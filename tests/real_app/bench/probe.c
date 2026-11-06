// The same sleep as the Python probe, on a thread holding no GIL, for what the OS alone costs.
#define _GNU_SOURCE
#include <time.h>
#include <stdint.h>

static inline int64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000000000LL + t.tv_nsec;
}

void sleep_overshoots(int count, int sleep_us, double *out_us) {
    struct timespec want = {0, sleep_us * 1000L};
    for (int i = 0; i < count; i++) {
        int64_t start = now_ns();
        nanosleep(&want, NULL);
        out_us[i] = (now_ns() - start) / 1000.0 - sleep_us;
    }
}
