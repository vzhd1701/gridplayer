import objc

from Foundation import NSBundle, NSWorkspace

from gridplayer.version import __app_id__


def is_the_only_instance():
    instances_count = sum(
        app.bundleIdentifier() == __app_id__
        for app in NSWorkspace.sharedWorkspace().runningApplications()
    )

    return instances_count == 1


# stolen from
# https://github.com/munki/munki/blob/main/code/client/munkilib/powermgr.py
# needs pyobjc-core, pyobjc-framework-Cocoa

# See http://michaellynn.github.io/2015/08/08/learn-you-a-better-pyobjc-bridgesupport-signature/
# for a primer on the bridging techniques used here

# https://developer.apple.com/documentation/iokit/iopowersources.h?language=objc
IOKit = NSBundle.bundleWithIdentifier_("com.apple.framework.IOKit")

functions = [
    ("IOPMAssertionCreateWithName", b"i@i@o^i"),
    ("IOPMAssertionRelease", b"vi"),
    ("IOPSGetPowerSourceDescription", b"@@@"),
    ("IOPSCopyPowerSourcesInfo", b"@"),
    ("IOPSCopyPowerSourcesList", b"@@"),
    ("IOPSGetProvidingPowerSourceType", b"@@"),
]

objc.loadBundleFunctions(IOKit, globals(), functions)


def assertNoIdleSleep(reason=None):
    """Uses IOKit functions to prevent idle sleep."""
    kIOPMAssertionTypeNoIdleSleep = "NoIdleSleepAssertion"
    kIOPMAssertionLevelOn = 255

    if not reason:
        reason = "Some reason"
    # pylint: disable=undefined-variable
    errcode, assertID = IOPMAssertionCreateWithName(
        kIOPMAssertionTypeNoIdleSleep, kIOPMAssertionLevelOn, reason, None
    )
    # pylint: enable=undefined-variable
    if errcode:
        return None
    return assertID


def removeNoIdleSleepAssertion(assertion_id):
    """Uses IOKit functions to remove a "no idle sleep" assertion."""
    if assertion_id:
        # pylint: disable=undefined-variable
        IOPMAssertionRelease(assertion_id)
