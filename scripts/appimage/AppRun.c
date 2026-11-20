/**************************************************************************

Copyright (c) 2004-18 Simon Peter
Portions Copyright (c) 2010 RazZziel

All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

**************************************************************************/

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <link.h>
#include <unistd.h>
#include <libgen.h>
#include <dirent.h>
#include <string.h>
#include <errno.h>
#include <dlfcn.h>

#define die(...)                                    \
    do {                                            \
        fprintf(stderr, "Error: " __VA_ARGS__);     \
        exit(1);                                    \
    } while(0);
#define SET_NEW_ENV(str,len,fmt,...)                \
    format = fmt;                                   \
    length = strlen(format) + (len);                \
    char *str = calloc(length, sizeof(char));     \
    snprintf(str, length, format, __VA_ARGS__);   \
    putenv(str);
#define MAX(a,b)    (a > b ? a : b)
#define bool int
#define false 0
#define true -1

#define LINE_SIZE 255

/* Python, from the AppDir: build_docker.sh passes it as -DPYTHON_BIN */
#ifndef PYTHON_BIN
#error "PYTHON_BIN not given"
#endif

/* Debian's name for the architecture's folders, x86_64-linux-gnu */
#ifndef MULTIARCH
#error "MULTIARCH not given"
#endif

/* The names of the variables changed here, ":" between them; the system's
   value of each it had is kept as GRIDPLAYER_HOST_<name> */
char host_vars[1024] = "";

void keep_host(const char *name) {
    if (host_vars[0])
        strncat(host_vars, ":", sizeof(host_vars) - strlen(host_vars) - 1);
    strncat(host_vars, name, sizeof(host_vars) - strlen(host_vars) - 1);

    const char *value = getenv(name);

    if (value) {
        char kept[256];
        snprintf(kept, sizeof(kept), "GRIDPLAYER_HOST_%s", name);
        setenv(kept, value, 1);
    }
}

int filter(const struct dirent *dir) {
    char *p = (char*) &dir->d_name;
    p = strrchr(p, '.');
    return p && !strcmp(p, ".desktop");
}

/* The file a path leads to past its links, by name alone, which has the
   version: libva.so.2 -> libva.so.2.2000.0. NULL if it leads nowhere. */
char *file_name(const char *path) {
    char *real = realpath(path, NULL);

    if (!real)
        return NULL;

    char *name = strdup(strrchr(real, '/') + 1);
    free(real);

    return name;
}

/* The system's copy of a library, by name: NULL if it has none */
char *system_file_name(const char *soname) {
    void *handle = dlopen(soname, RTLD_LAZY | RTLD_LOCAL);

    if (!handle)
        return NULL;

    char *name = NULL;
    struct link_map *map;

    if (dlinfo(handle, RTLD_DI_LINKMAP, &map) == 0)
        name = file_name(map->l_name);

    dlclose(handle);

    return name;
}

/* Libraries a system has as a rule, whose drivers and plugins are its own:
   libva and VAAPI drivers, Mesa and libwayland, PipeWire and its plugins. The
   system's copy goes with them, unless ours is newer: a library of ours may
   need what only the newer has (ffmpeg's libavutil, vaMapBuffer2 of libva
   2.21). Each is kept in usr/lib/fallback/<its name>/, and goes on the path
   only when the system has none or an older one. */
char *needed_fallbacks(const char *appdir, bool *own_libva) {
    size_t dir_s = strlen(appdir) + 20;
    char *dir = calloc(dir_s, sizeof(char));
    snprintf(dir, dir_s, "%s/usr/lib/fallback", appdir);

    char *paths = calloc(1, sizeof(char));
    size_t paths_s = 1;

    *own_libva = false;

    struct dirent **names;
    int count = scandir(dir, &names, NULL, alphasort);

    for (int i = 0; i < count; i++) {
        char *soname = names[i]->d_name;

        if (soname[0] != '.') {
            size_t ours_s = strlen(dir) + strlen(soname) * 2 + 3;
            char *ours_path = calloc(ours_s, sizeof(char));
            snprintf(ours_path, ours_s, "%s/%s/%s", dir, soname, soname);

            char *ours = file_name(ours_path);
            char *systems = system_file_name(soname);

            // JACK's only where the system has none: ours is PipeWire's, whose
            // version reads higher than JACK2's own and serves no JACK server
            bool by_version = strcmp(soname, "libjack.so.0") != 0;

            if (ours && (!systems || (by_version && strverscmp(systems, ours) < 0))) {
                paths_s += strlen(dir) + strlen(soname) + 2;
                paths = realloc(paths, paths_s);
                strcat(paths, dir);
                strcat(paths, "/");
                strcat(paths, soname);
                strcat(paths, ":");

                if (!strcmp(soname, "libva.so.2"))
                    *own_libva = true;
            }

            free(ours);
            free(systems);
            free(ours_path);
        }

        free(names[i]);
    }

    if (count > 0)
        free(names);

    free(dir);

    return paths;
}

int main(int argc, char *argv[]) {
    char *appdir = dirname(realpath("/proc/self/exe", NULL));
    if (!appdir)
        die("Could not access /proc/self/exe\n");

    int ret;
    struct dirent **namelist;
    ret = scandir(appdir, &namelist, filter, NULL);

    if (ret == 0) {
        die("No .desktop files found\n");
    } else if(ret == -1) {
        die("Could not scan directory %s\n", appdir);
    }

    /* Extract executable from .desktop file */
    char *desktop_file = calloc(LINE_SIZE, sizeof(char));
    snprintf(desktop_file, LINE_SIZE, "%s/%s", appdir, namelist[0]->d_name);
    FILE *f     = fopen(desktop_file, "r");
    char *line  = malloc(LINE_SIZE);
    size_t n    = LINE_SIZE;

    do {
        if (getline(&line, &n, f) == -1)
            die("Executable not found, make sure there is a line starting with 'Exec='\n");
    } while(strncmp(line, "Exec=", 5));
    fclose(f);
    char *exe   = line+5;

    // parse arguments
    bool in_quotes = 0;
    for (n = 0; n < LINE_SIZE; n++) {
        if (!line[n])         // end of string
            break;
        else if (line[n] == 10 || line[n] == 13) {
            line[n] = '\0';
            line[n+1] = '\0';
            line[n+2] = '\0';
            break;
        } else if (line[n] == '"') {
            in_quotes = !in_quotes;
        } else if (line[n] == ' ' && !in_quotes)
            line[n] = '\0';
    }

    // count arguments
    char*   arg         = exe;
    int     argcount    = 0;
    while ((arg += (strlen(arg)+1)) && *arg)
        argcount += 1;

    // merge args
    char*   outargptrs[argcount + argc + 1];
    outargptrs[0] = exe;
    int     outargindex = 1;
    arg                 = exe;
    int     argc_       = argc - 1;     // argv[0] is the filename
    char**  argv_       = argv + 1;
    while ((arg += (strlen(arg)+1)) && *arg) {
        if (arg[0] == '%' || (arg[0] == '"' && arg[1] == '%')) {         // handle desktop file field codes
            char code = arg[arg[0] == '%' ? 1 : 2];
            switch(code) {
                case 'f':
                case 'u':
                    if (argc_ > 0) {
                        outargptrs[outargindex++] = *argv_++;
                        argc_--;
                    }
                    break;
                case 'F':
                case 'U':
                    while (argc_ > 0) {
                        outargptrs[outargindex++] = *argv_++;
                        argc_--;
                    }
                    break;
                case 'i':
                case 'c':
                case 'k':
                    fprintf(stderr, "WARNING: Desktop file field code %%%c is not currently supported\n", code);
                    break;
                default:
                    fprintf(stderr, "WARNING: Invalid desktop file field code %%%c\n", code);
                    break;
            }
        } else {
            outargptrs[outargindex++] = arg;
        }
    }
    while (argc_ > 0) {
        outargptrs[outargindex++] = *argv_++;
        argc_--;
    }
    outargptrs[outargindex] = '\0';     // trailing null argument required by execvp()

    // The folder it was started in is kept: a file named on the command line
    // is found from there, as with any other program
    size_t appdir_s = strlen(appdir);

    // set environment variables
    char *old_env;
    size_t length;
    const char *format;

    // the AppImage's runtime sets it, but not to an AppDir run as it is (an
    // AppImage unpacked with --appimage-extract): the app finds its VLC by it
    setenv("APPDIR", appdir, 0);

    old_env = getenv("PATH") ?: "";
    keep_host("PATH");
    SET_NEW_ENV(new_path, appdir_s + strlen(old_env), "PATH=%s/usr/bin/:%s", appdir, old_env);

    // asked before LD_LIBRARY_PATH changes, of the system alone
    bool own_libva;
    char *fallbacks = needed_fallbacks(appdir, &own_libva);

    // ours looks for VAAPI drivers where EL9 keeps them; the system's are
    // older than it, which libva takes
    if (own_libva && !getenv("LIBVA_DRIVERS_PATH")) {
        keep_host("LIBVA_DRIVERS_PATH");
        putenv("LIBVA_DRIVERS_PATH=/usr/lib/" MULTIARCH "/dri:/usr/lib64/dri:/usr/lib/dri:/run/opengl-driver/lib/dri");
    }

    old_env = getenv("LD_LIBRARY_PATH") ?: "";
    keep_host("LD_LIBRARY_PATH");
    SET_NEW_ENV(new_ld_library_path, appdir_s*2 + strlen(fallbacks) + strlen(old_env), "LD_LIBRARY_PATH=%s/usr/lib/:%s/usr/lib/vlc:%s%s", appdir, appdir, fallbacks, old_env);

    old_env = getenv("XDG_DATA_DIRS") ?: "/usr/local/share/:/usr/share/";
    keep_host("XDG_DATA_DIRS");
    SET_NEW_ENV(new_xdg_data_dirs, appdir_s + strlen(old_env), "XDG_DATA_DIRS=%s/usr/share/:%s", appdir, old_env);

    keep_host("SSL_CERT_FILE");
    SET_NEW_ENV(ssl_cert_file_path, appdir_s, "SSL_CERT_FILE=%s/opt/_internal/certs.pem", appdir);

    /* Otherwise may get errors because Python cannot write __pycache__ bytecode cache */
    keep_host("PYTHONDONTWRITEBYTECODE");
    putenv("PYTHONDONTWRITEBYTECODE=1");

    // what the app takes away again for a program of the system it starts
    // (xdg-open), see gridplayer/utils/host_env.py
    setenv("GRIDPLAYER_HOST_VARS", host_vars, 1);

    /* Run: the script with our Python. Not the script itself, whose first
       lines are a shell's, running the system's readlink and dirname with
       our libraries on the path: Ubuntu's Rust coreutils fail on them. */
    size_t python_s = appdir_s + strlen(PYTHON_BIN) + 2;
    char *python = calloc(python_s, sizeof(char));
    snprintf(python, python_s, "%s/%s", appdir, PYTHON_BIN);

    size_t script_s = appdir_s + strlen(exe) + 10;
    char *script = calloc(script_s, sizeof(char));
    snprintf(script, script_s, "%s/usr/bin/%s", appdir, exe);

    char *python_args[outargindex + 2];
    python_args[0] = python;
    python_args[1] = script;
    for (int i = 1; i <= outargindex; i++)
        python_args[i + 1] = outargptrs[i];

    ret = execv(python, python_args);

    int error = errno;

    if (ret == -1)
        die("Error executing '%s': %s\n", python, strerror(error));

    free(line);
    free(desktop_file);
    free(new_path);
    free(new_ld_library_path);
    free(new_xdg_data_dirs);
    free(ssl_cert_file_path);
    free(python);
    free(script);
    return 0;
}
