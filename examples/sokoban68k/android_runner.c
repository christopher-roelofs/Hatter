/* Run the APK's exported CLI in a separate shell process for headless tests.
 * No JNI activity, app data directory, or installed-device state is touched. */
#include <dlfcn.h>
#include <stdio.h>
int main(int argc, char **argv) {
    void *library = dlopen("libmcap.so", RTLD_NOW | RTLD_GLOBAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 2; }
    int (*launch)(int,char **) = (int (*)(int,char **))dlsym(library,"mrc_launch_main");
    if (!launch) { fprintf(stderr, "%s\n", dlerror()); return 2; }
    return launch(argc,argv);
}
