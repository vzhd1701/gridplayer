import objc
from Foundation import NSBundle

# stolen from
# https://github.com/munki/munki/blob/main/code/client/munkilib/powermgr.py
# needs pyobjc-core, pyobjc-framework-Cocoa

# http://michaellynn.github.io/2015/08/08/learn-you-a-better-pyobjc-bridgesupport-signature/
# see for a primer on the bridging techniques used here

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

objc.loadBundleFunctions(IOKit, globals(), functions)  # noqa: WPS421


def assertNoIdleSleep(reason=None):
    """Uses IOKit functions to prevent idle sleep."""
    kIOPMAssertionTypeNoIdleSleep = "NoIdleSleepAssertion"
    kIOPMAssertionLevelOn = 255

    if not reason:
        reason = "Some reason"
    errcode, assertID = IOPMAssertionCreateWithName(  # noqa: F821
        kIOPMAssertionTypeNoIdleSleep, kIOPMAssertionLevelOn, reason, None
    )
    if errcode:
        return None
    return assertID


def removeNoIdleSleepAssertion(assertion_id):
    """Uses IOKit functions to remove a "no idle sleep" assertion."""
    if assertion_id:
        IOPMAssertionRelease(assertion_id)  # noqa: F821
