// The app's mpv path with no Python in it: the same options, an event thread per player, render
// threads with their own EGL context, render then glReadPixels for each new frame.
//
// native_bench CLIP CELLS W H SECONDS HWDEC RENDER_THREADS OBSERVE_TIME
//
// Prints one JSON line. It's the control for what Python and the GIL cost.
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <GL/gl.h>
#include <X11/Xlib.h>
#include <locale.h>
#include <mpv/client.h>
#include <mpv/render_gl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAX_CELLS 128
#define MAX_RENDER_THREADS 8

typedef void (*GenFramebuffersFn)(GLsizei, GLuint *);
typedef void (*BindFramebufferFn)(GLenum, GLuint);
typedef void (*FramebufferTexture2DFn)(GLenum, GLenum, GLenum, GLuint, GLint);
#define GL_FRAMEBUFFER_ 0x8D40
#define GL_COLOR_ATTACHMENT0_ 0x8CE0
#define GL_BGRA_ 0x80E1
#define GL_RGBA8_ 0x8058
#define GL_PIXEL_PACK_BUFFER_ 0x88EB
#define GL_STREAM_READ_ 0x88E1
#define GL_READ_ONLY_ 0x88B8
#define GL_SYNC_GPU_COMMANDS_COMPLETE_ 0x9117
#define GL_SYNC_FLUSH_COMMANDS_BIT_ 0x00000001
typedef void (*GenBuffersFn)(GLsizei, GLuint *);
typedef void (*BindBufferFn)(GLenum, GLuint);
typedef void (*BufferDataFn)(GLenum, ptrdiff_t, const void *, GLenum);
typedef void *(*MapBufferFn)(GLenum, GLenum);
typedef GLboolean (*UnmapBufferFn)(GLenum);
typedef void *(*FenceSyncFn)(GLenum, GLbitfield);
typedef GLenum (*ClientWaitSyncFn)(void *, GLbitfield, uint64_t);
typedef void (*DeleteSyncFn)(void *);

struct renderer;

struct cell {
    mpv_handle *mpv;
    mpv_render_context *ctx;
    struct renderer *renderer;
    atomic_int needs_update;
    atomic_long frames;
    GLuint texture;
    GLuint pbo;
    unsigned char *pixels;
    pthread_t events;
};

struct renderer {
    int index;
    pthread_t thread;
    pthread_mutex_t lock;
    pthread_cond_t cond;
    int woken;
    struct cell *cells[MAX_CELLS];
    int count;
    clockid_t cpu_clock;
    double render_s, read_s;
};

static struct cell cells[MAX_CELLS];
static struct renderer renderers[MAX_RENDER_THREADS];
static int cell_count, width, height, render_threads, observe_time;
static const char *clip, *hwdec;
static atomic_int stopping, measuring;
static int use_pbo;

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static void *get_proc(void *ctx, const char *name) {
    (void)ctx;
    return (void *)eglGetProcAddress(name);
}

static void on_update(void *data) {
    struct cell *cell = data;
    struct renderer *r = cell->renderer;
    atomic_store(&cell->needs_update, 1);
    pthread_mutex_lock(&r->lock);
    r->woken = 1;
    pthread_cond_signal(&r->cond);
    pthread_mutex_unlock(&r->lock);
}

static void set(mpv_handle *mpv, const char *name, const char *value) {
    if (mpv_set_option_string(mpv, name, value) < 0) {
        fprintf(stderr, "option %s=%s refused\n", name, value);
    }
}

static void make_player(struct cell *cell) {
    mpv_handle *mpv = mpv_create();
    set(mpv, "vo", "libmpv");
    set(mpv, "hwdec", hwdec);
    set(mpv, "hwdec-extra-frames", "0");
    set(mpv, "vd-lavc-threads", "4");
    set(mpv, "video-timing-offset", "0");
    set(mpv, "keepaspect", "no");
    set(mpv, "profile", "fast");
    set(mpv, "loop-file", "inf");
    set(mpv, "keep-open", "always");
    set(mpv, "mute", "yes");
    set(mpv, "osd-level", "0");
    set(mpv, "demuxer-max-bytes", "32MiB");
    set(mpv, "demuxer-max-back-bytes", "16MiB");
    set(mpv, "input-default-bindings", "no");
    set(mpv, "input-vo-keyboard", "no");
    set(mpv, "ytdl", "no");
    set(mpv, "audio-file-auto", "no");
    set(mpv, "sub-auto", "no");
    set(mpv, "cover-art-auto", "no");
    set(mpv, "load-scripts", "no");
    set(mpv, "ao", "null");
    if (getenv("OPTS")) {
        char *copy = strdup(getenv("OPTS")), *save = NULL;
        for (char *item = strtok_r(copy, ";", &save); item; item = strtok_r(NULL, ";", &save)) {
            char *eq = strchr(item, '=');
            if (eq) {
                *eq = 0;
                set(mpv, item, eq + 1);
            }
        }
        free(copy);
    }
    if (mpv_initialize(mpv) < 0) {
        fprintf(stderr, "mpv_initialize failed\n");
        exit(1);
    }
    cell->mpv = mpv;
}

static void *event_thread(void *data) {
    struct cell *cell = data;
    if (observe_time) {
        mpv_observe_property(cell->mpv, 1, "time-pos", MPV_FORMAT_DOUBLE);
    }
    while (!atomic_load(&stopping)) {
        mpv_event *event = mpv_wait_event(cell->mpv, 0.5);
        if (event->event_id == MPV_EVENT_SHUTDOWN) {
            break;
        }
    }
    return NULL;
}

static void *render_thread(void *data) {
    struct renderer *r = data;

    Display *x = XOpenDisplay(NULL);
    if (!x) {
        fprintf(stderr, "no X display\n");
        exit(1);
    }
    EGLDisplay display = eglGetDisplay((EGLNativeDisplayType)x);
    eglInitialize(display, NULL, NULL);
    eglBindAPI(EGL_OPENGL_API);
    EGLint attrs[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
                      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE};
    EGLConfig config;
    EGLint found = 0;
    eglChooseConfig(display, attrs, &config, 1, &found);
    EGLint pbuffer[] = {EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE};
    EGLSurface surface = eglCreatePbufferSurface(display, config, pbuffer);
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, NULL);
    if (!eglMakeCurrent(display, surface, surface, context)) {
        fprintf(stderr, "no GL context\n");
        exit(1);
    }

    GenFramebuffersFn genFramebuffers = (GenFramebuffersFn)eglGetProcAddress("glGenFramebuffers");
    BindFramebufferFn bindFramebuffer = (BindFramebufferFn)eglGetProcAddress("glBindFramebuffer");
    FramebufferTexture2DFn framebufferTexture =
        (FramebufferTexture2DFn)eglGetProcAddress("glFramebufferTexture2D");

    GLuint fbo;
    genFramebuffers(1, &fbo);

    GenBuffersFn genBuffers = (GenBuffersFn)eglGetProcAddress("glGenBuffers");
    BindBufferFn bindBuffer = (BindBufferFn)eglGetProcAddress("glBindBuffer");
    BufferDataFn bufferData = (BufferDataFn)eglGetProcAddress("glBufferData");
    MapBufferFn mapBuffer = (MapBufferFn)eglGetProcAddress("glMapBuffer");
    UnmapBufferFn unmapBuffer = (UnmapBufferFn)eglGetProcAddress("glUnmapBuffer");
    FenceSyncFn fenceSync = (FenceSyncFn)eglGetProcAddress("glFenceSync");
    ClientWaitSyncFn clientWaitSync = (ClientWaitSyncFn)eglGetProcAddress("glClientWaitSync");
    DeleteSyncFn deleteSync = (DeleteSyncFn)eglGetProcAddress("glDeleteSync");

    pthread_getcpuclockid(pthread_self(), &r->cpu_clock);

    for (int i = 0; i < r->count; i++) {
        struct cell *cell = r->cells[i];
        mpv_opengl_init_params gl_init = {.get_proc_address = get_proc};
        int advanced = 1;
        mpv_render_param params[] = {
            {MPV_RENDER_PARAM_API_TYPE, (void *)MPV_RENDER_API_TYPE_OPENGL},
            {MPV_RENDER_PARAM_OPENGL_INIT_PARAMS, &gl_init},
            {MPV_RENDER_PARAM_ADVANCED_CONTROL, &advanced},
            {MPV_RENDER_PARAM_X11_DISPLAY, x},
            {MPV_RENDER_PARAM_INVALID, NULL},
        };
        if (mpv_render_context_create(&cell->ctx, cell->mpv, params) < 0) {
            fprintf(stderr, "no render context\n");
            exit(1);
        }
        mpv_render_context_set_update_callback(cell->ctx, on_update, cell);

        glGenTextures(1, &cell->texture);
        glBindTexture(GL_TEXTURE_2D, cell->texture);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8_, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
        cell->pixels = malloc((size_t)width * height * 4);
        if (use_pbo) {
            genBuffers(1, &cell->pbo);
            bindBuffer(GL_PIXEL_PACK_BUFFER_, cell->pbo);
            bufferData(GL_PIXEL_PACK_BUFFER_, (ptrdiff_t)width * height * 4, NULL, GL_STREAM_READ_);
            bindBuffer(GL_PIXEL_PACK_BUFFER_, 0);
        }

        const char *load[] = {"loadfile", clip, NULL};
        mpv_command_async(cell->mpv, 0, load);
        pthread_create(&cell->events, NULL, event_thread, cell);
    }

    while (!atomic_load(&stopping)) {
        pthread_mutex_lock(&r->lock);
        while (!r->woken && !atomic_load(&stopping)) {
            pthread_cond_wait(&r->cond, &r->lock);
        }
        r->woken = 0;
        pthread_mutex_unlock(&r->lock);

        struct cell *pending[MAX_CELLS];
        int pending_count = 0;

        for (int i = 0; i < r->count; i++) {
            struct cell *cell = r->cells[i];
            if (!atomic_exchange(&cell->needs_update, 0)) {
                continue;
            }
            uint64_t flags = mpv_render_context_update(cell->ctx);
            if (!(flags & MPV_RENDER_UPDATE_FRAME)) {
                continue;
            }
            double t0 = now();
            bindFramebuffer(GL_FRAMEBUFFER_, fbo);
            glBindTexture(GL_TEXTURE_2D, cell->texture);
            framebufferTexture(GL_FRAMEBUFFER_, GL_COLOR_ATTACHMENT0_, GL_TEXTURE_2D, cell->texture, 0);
            mpv_opengl_fbo target = {.fbo = (int)fbo, .w = width, .h = height, .internal_format = 0};
            int flip = 0, block = 0;
            mpv_render_param params[] = {
                {MPV_RENDER_PARAM_OPENGL_FBO, &target},
                {MPV_RENDER_PARAM_FLIP_Y, &flip},
                {MPV_RENDER_PARAM_BLOCK_FOR_TARGET_TIME, &block},
                {MPV_RENDER_PARAM_INVALID, NULL},
            };
            mpv_render_context_render(cell->ctx, params);
            double t1 = now();
            bindFramebuffer(GL_FRAMEBUFFER_, fbo);
            if (use_pbo) {
                bindBuffer(GL_PIXEL_PACK_BUFFER_, cell->pbo);
                glReadPixels(0, 0, width, height, GL_BGRA_, GL_UNSIGNED_BYTE, NULL);
                bindBuffer(GL_PIXEL_PACK_BUFFER_, 0);
                pending[pending_count++] = cell;
            } else {
                glReadPixels(0, 0, width, height, GL_BGRA_, GL_UNSIGNED_BYTE, cell->pixels);
                atomic_fetch_add(&cell->frames, 1);
            }
            double t2 = now();
            if (atomic_load(&measuring)) {
                r->render_s += t1 - t0;
                r->read_s += t2 - t1;
            }
        }

        if (pending_count) {
            double t0 = now();
            void *sync = fenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE_, 0);
            clientWaitSync(sync, GL_SYNC_FLUSH_COMMANDS_BIT_, 1000000000ULL);
            deleteSync(sync);
            for (int i = 0; i < pending_count; i++) {
                struct cell *cell = pending[i];
                bindBuffer(GL_PIXEL_PACK_BUFFER_, cell->pbo);
                void *mapped = mapBuffer(GL_PIXEL_PACK_BUFFER_, GL_READ_ONLY_);
                if (mapped) {
                    memcpy(cell->pixels, mapped, (size_t)width * height * 4);
                    unmapBuffer(GL_PIXEL_PACK_BUFFER_);
                }
                bindBuffer(GL_PIXEL_PACK_BUFFER_, 0);
                atomic_fetch_add(&cell->frames, 1);
            }
            if (atomic_load(&measuring)) {
                r->read_s += now() - t0;
            }
        }
    }

    // the process ends here, nothing is freed in order
    return NULL;
}

static double cpu_of(clockid_t clock) {
    struct timespec t;
    clock_gettime(clock, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static long get_count(mpv_handle *mpv, const char *name) {
    int64_t value = 0;
    mpv_get_property(mpv, name, MPV_FORMAT_INT64, &value);
    return (long)value;
}

int main(int argc, char **argv) {
    if (argc < 9) {
        fprintf(stderr, "usage: native_bench CLIP CELLS W H SECONDS HWDEC RENDER_THREADS OBSERVE\n");
        return 2;
    }
    XInitThreads();
    setlocale(LC_NUMERIC, "C");
    clip = argv[1];
    cell_count = atoi(argv[2]);
    width = atoi(argv[3]);
    height = atoi(argv[4]);
    double seconds = atof(argv[5]);
    hwdec = argv[6];
    render_threads = atoi(argv[7]);
    observe_time = atoi(argv[8]);
    double settle = getenv("SETTLE") ? atof(getenv("SETTLE")) : 8;
    use_pbo = getenv("PBO") != NULL;

    for (int i = 0; i < render_threads; i++) {
        pthread_mutex_init(&renderers[i].lock, NULL);
        pthread_cond_init(&renderers[i].cond, NULL);
        renderers[i].index = i;
    }
    for (int i = 0; i < cell_count; i++) {
        struct renderer *r = &renderers[i % render_threads];
        cells[i].renderer = r;
        r->cells[r->count++] = &cells[i];
        make_player(&cells[i]);
    }
    for (int i = 0; i < render_threads; i++) {
        pthread_create(&renderers[i].thread, NULL, render_thread, &renderers[i]);
    }

    double t_settle = now();
    while (now() - t_settle < settle) {
        usleep(100000);
    }

    long start_frames[MAX_CELLS], start_drops[MAX_CELLS], start_dec_drops[MAX_CELLS];
    double start_pos[MAX_CELLS];
    for (int i = 0; i < cell_count; i++) {
        start_frames[i] = atomic_load(&cells[i].frames);
        start_drops[i] = get_count(cells[i].mpv, "frame-drop-count");
        start_dec_drops[i] = get_count(cells[i].mpv, "decoder-frame-drop-count");
        mpv_get_property(cells[i].mpv, "time-pos", MPV_FORMAT_DOUBLE, &start_pos[i]);
    }
    double start_render_cpu[MAX_RENDER_THREADS];
    for (int i = 0; i < render_threads; i++) {
        start_render_cpu[i] = cpu_of(renderers[i].cpu_clock);
    }
    double start_cpu = cpu_of(CLOCK_PROCESS_CPUTIME_ID);
    atomic_store(&measuring, 1);
    double t0 = now();

    usleep((useconds_t)(seconds * 1e6));

    double span = now() - t0;
    atomic_store(&measuring, 0);
    double cpu = cpu_of(CLOCK_PROCESS_CPUTIME_ID) - start_cpu;

    double total = 0, worst = 1e9;
    long drops = 0, dec_drops = 0;
    double clock_sum = 0;
    int clock_count = 0;
    for (int i = 0; i < cell_count; i++) {
        double fps = (atomic_load(&cells[i].frames) - start_frames[i]) / span;
        total += fps;
        if (fps < worst) worst = fps;
        drops += get_count(cells[i].mpv, "frame-drop-count") - start_drops[i];
        dec_drops += get_count(cells[i].mpv, "decoder-frame-drop-count") - start_dec_drops[i];
        double pos = 0;
        mpv_get_property(cells[i].mpv, "time-pos", MPV_FORMAT_DOUBLE, &pos);
        if (pos >= start_pos[i]) {
            clock_sum += (pos - start_pos[i]) / span;
            clock_count++;
        }
    }
    double render_cpu = 0, render_s = 0, read_s = 0;
    for (int i = 0; i < render_threads; i++) {
        render_cpu += cpu_of(renderers[i].cpu_clock) - start_render_cpu[i];
        render_s += renderers[i].render_s;
        read_s += renderers[i].read_s;
    }

    char *current = mpv_get_property_string(cells[0].mpv, "hwdec-current");

    printf("{\"cells\":%d,\"size\":\"%dx%d\",\"hwdec\":\"%s\",\"render_threads\":%d,\"observe\":%d,\"pbo\":%d,"
           "\"fps_mean\":%.1f,\"fps_min\":%.1f,\"drops_per_s\":%.1f,\"dec_drops_per_s\":%.1f,\"clock\":%.3f,\"cpu_pct\":%.1f,\"render_cpu_pct\":%.1f,"
           "\"render_call_share\":%.1f,\"read_call_share\":%.1f}\n",
           cell_count, width, height, current ? current : "?", render_threads, observe_time, use_pbo, total / cell_count,
           worst, drops / span, dec_drops / span, clock_count ? clock_sum / clock_count : 0, cpu / span * 100, render_cpu / span * 100, render_s / span * 100, read_s / span * 100);
    fflush(stdout);
    _exit(0);
}
