/* Background input helper for Epic Seven under Proton/Wine.
 *
 * Runs inside the game's own Wine session and posts window messages to the
 * game window, so neither the real pointer nor keyboard focus is used.
 * Line protocol on stdin/stdout, client-pixel coordinates:
 *   find                       -> "window HWND WIDTH HEIGHT" | "err ..."
 *   click X Y                  -> "ok" | "err ..."
 *   move X Y                   -> "ok" | "err ..."
 *   drag X1 Y1 X2 Y2 MS        -> "ok" | "err ..."
 *   release                    -> "ok"   (button-up at the last position)
 *   quit
 * Every action re-checks that the window found by "find" still exists, is not
 * minimized and still has the same client size. Build:
 *   x86_64-w64-mingw32-gcc -O2 -o e7_wine_input.exe e7_wine_input.c
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>

static HWND game;
static LONG game_w, game_h;
static int last_x, last_y, button_down;

static BOOL CALLBACK find_cb(HWND h, LPARAM unused) {
    char cls[64] = "", title[64] = "";
    (void)unused;
    GetClassNameA(h, cls, sizeof cls);
    GetWindowTextA(h, title, sizeof title);
    if (IsWindowVisible(h) && !strcmp(title, "Epic Seven") && !strncmp(cls, "GLFW", 4)) {
        game = h;
        return FALSE;
    }
    return TRUE;
}

static const char *check(int x, int y) {
    RECT r;
    if (!game || !IsWindow(game)) return "game window is gone";
    if (IsIconic(game)) return "game window is minimized";
    if (!GetClientRect(game, &r) || r.right != game_w || r.bottom != game_h) return "game window was resized";
    if (x < 0 || y < 0 || x >= game_w || y >= game_h) return "target is outside the game window";
    return NULL;
}

static void post(UINT msg, WPARAM wp, int x, int y) {
    PostMessageA(game, msg, wp, MAKELPARAM(x, y));
    last_x = x; last_y = y;
}

static void up(void) {
    if (button_down) { post(WM_LBUTTONUP, 0, last_x, last_y); button_down = 0; }
}

int main(void) {
    char line[256];
    setvbuf(stdout, NULL, _IONBF, 0);
    while (fgets(line, sizeof line, stdin)) {
        int x, y, x2, y2, ms;
        const char *problem;
        if (!strncmp(line, "quit", 4)) break;
        if (!strncmp(line, "find", 4)) {
            RECT r; game = NULL;
            EnumWindows(find_cb, 0);
            if (!game) { printf("err Epic Seven window not found\n"); continue; }
            GetClientRect(game, &r); game_w = r.right; game_h = r.bottom;
            printf("window %llu %ld %ld\n", (unsigned long long)(ULONG_PTR)game, game_w, game_h);
        } else if (!strncmp(line, "release", 7)) {
            if (game && IsWindow(game)) up();
            printf("ok\n");
        } else if (sscanf(line, "click %d %d", &x, &y) == 2) {
            if ((problem = check(x, y))) { printf("err %s\n", problem); continue; }
            post(WM_MOUSEMOVE, 0, x, y); Sleep(30);
            post(WM_LBUTTONDOWN, MK_LBUTTON, x, y); button_down = 1; Sleep(80);
            up();
            printf("ok\n");
        } else if (sscanf(line, "move %d %d", &x, &y) == 2) {
            if ((problem = check(x, y))) { printf("err %s\n", problem); continue; }
            post(WM_MOUSEMOVE, 0, x, y);
            printf("ok\n");
        } else if (sscanf(line, "drag %d %d %d %d %d", &x, &y, &x2, &y2, &ms) == 5) {
            int steps, i;
            if ((problem = check(x, y)) || (problem = check(x2, y2))) { printf("err %s\n", problem); continue; }
            if (ms < 100 || ms > 1000) { printf("err invalid drag duration\n"); continue; }
            steps = ms / 16; if (steps < 6) steps = 6;
            post(WM_MOUSEMOVE, 0, x, y); Sleep(30);
            post(WM_LBUTTONDOWN, MK_LBUTTON, x, y); button_down = 1; Sleep(40);
            for (i = 1; i <= steps; i++) {
                if ((problem = check(x, y))) break;
                post(WM_MOUSEMOVE, MK_LBUTTON, x + (x2 - x) * i / steps, y + (y2 - y) * i / steps);
                Sleep(ms / steps);
            }
            Sleep(60);
            up();
            if (problem) printf("err %s\n", problem); else printf("ok\n");
        } else {
            printf("err unknown command\n");
        }
    }
    if (game && IsWindow(game)) up();
    return 0;
}
