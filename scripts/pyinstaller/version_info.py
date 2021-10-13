# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx

VSVersionInfo(
    ffi=FixedFileInfo(
        # filevers and prodvers should be always a tuple with four items: (1, 2, 3, 4)
        # Set not needed items to zero 0. Must always contain 4 elements.
        filevers=(
            int("{APP_VERSION}".split(".")[0]),
            int("{APP_VERSION}".split(".")[1]),
            int("{APP_VERSION}".split(".")[2]),
            0,
        ),
        prodvers=(
            int("{APP_VERSION}".split(".")[0]),
            int("{APP_VERSION}".split(".")[1]),
            int("{APP_VERSION}".split(".")[2]),
            0,
        ),
        # Contains a bitmask that specifies the valid bits 'flags'r
        mask=0x3F,
        # Contains a bitmask that specifies the Boolean attributes of the file.
        flags=0x0,
        # The operating system for which this file was designed.
        # 0x4 - NT and there is no need to change it.
        OS=0x40004,
        # The general type of file.
        # 0x1 - the file is an application.
        fileType=0x1,
        # The function of the file.
        # 0x0 - the function is not defined for this fileType
        subtype=0x0,
        # Creation date and time stamp.
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "{APP_AUTHOR}"),
                        StringStruct("FileDescription", "{APP_DISP_NAME}"),
                        StringStruct("FileVersion", "{APP_VERSION}.0"),
                        StringStruct("InternalName", "{APP_NAME}"),
                        StringStruct(
                            "LegalCopyright", "© {APP_AUTHOR}. All rights reserved."
                        ),
                        StringStruct("OriginalFilename", "{APP_NAME}.exe"),
                        StringStruct("ProductName", "{APP_DISP_NAME}"),
                        StringStruct("ProductVersion", "{APP_VERSION}.0"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)
