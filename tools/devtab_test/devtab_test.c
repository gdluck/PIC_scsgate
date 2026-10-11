/* Host-side replay of the PIC_scsgate device-table classifier (OutputMapping) against the
 * firmware corpus.  Build:  make   (needs classifier.inc, produced by extract.py from ESPSCSGATE.C)
 *
 * Usage: ./devtab_test hex2own_corpus.tsv      -> checks every frame, prints mismatches and totals
 *        echo B8311200 | ./devtab_test -       -> prints the device table entry a frame produces
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

typedef unsigned char BYTE;
typedef unsigned short WORD;
typedef union { struct { BYTE devType; }; BYTE all; } DEVICE;
typedef union { struct { BYTE LS:4, MS:4; } half; struct { BYTE b0:1,b1:1,b2:1,b3:1,b4:1,b5:1,b6:1,b7:1; } bits; BYTE Val; } BYTE_VAL;

#define DEV_NR 210
#define MAXTAPP 25
#define UP 8
#define DOWN 9
#define STOP 0x0A
#define SCSBUFMAX 10
#define SCSBUFLEN 16
#define DEVT_SWITCH 0x01
#define DEVT_DIMMER 0x03
#define DEVT_COVER 0x08
#define DEVT_COVER_PCT 0x09
#define DEVT_GENERIC 0x0B
#define DEVT_ALARM 0x0E
#define DEVT_THERMO 0x0F
#define DEVT_ENERGY 0x10

DEVICE devc[DEV_NR];
BYTE didx;
BYTE scsMessageRx[SCSBUFMAX][SCSBUFLEN];
BYTE rBufferIdxR = 0;
BYTE auto_ack_low = 0, auto_ack_high = 0;
struct { BYTE tapparelle_pct; } opt;
struct { BYTE device; WORD maxposition; } devicetappa[MAXTAPP];
struct { BYTE_VAL direction; WORD position, request; BYTE timeout; } tapparella[MAXTAPP];
BYTE maxtapp = 0, ixTapp;
union { struct { BYTE TopByte; }; BYTE data[16]; } dataByte;
int acks = 0;
void queueWrite(char len) { (void)len; acks++; }
void CmdTotaleTapparelle(BYTE c) { (void)c; }

static void classify(const BYTE *body, int n)
{
    BYTE f, chk = 0, i;
    BYTE tmpdest = 0, tmpfrom = 0, tmptype = 0, tmpcmd = 0, tmpbus = 0xFF;
    BYTE tmpext = 0, tmpsys = 0, tmpdim = 0, tmpb1 = 0, tmpraw = 0;
    (void)tmpbus; (void)f;
    for (i = 0; i < n; i++) chk ^= body[i];
    scsMessageRx[rBufferIdxR][0] = n + 3;
    scsMessageRx[rBufferIdxR][1] = 0xA8;
    memcpy(&scsMessageRx[rBufferIdxR][2], body, n);
    scsMessageRx[rBufferIdxR][2 + n] = chk;
    scsMessageRx[rBufferIdxR][3 + n] = 0xA3;
#include "classifier.inc"
}

static int hex2bytes(const char *s, BYTE *out)
{
    int n = 0, hi = -1;
    for (; *s; s++) {
        int v;
        if (isxdigit((unsigned char)*s)) v = isdigit((unsigned char)*s) ? *s - '0' : (toupper((unsigned char)*s) - 'A' + 10);
        else continue;
        if (hi < 0) hi = v; else { out[n++] = hi * 16 + v; hi = -1; if (n >= 8) break; }
    }
    return n;
}

/* expected type from the OWN messages the firmware emits for the frame (0 = no expectation) */
static int expected(const BYTE *b, int n, const char *own, BYTE *addr)
{
    int who = -1; const char *p = own;
    if (p[0] == '*' && p[1] == '#') p += 2; else if (p[0] == '*') p += 1;
    who = atoi(p);
    if (n == 4) {
        if ((b[2] & 0xF0) == 0x30 && who == 4) {           /* thermo short frame: zone in byte 1 */
            *addr = b[1];
            if (b[0] == 0x9D || b[0] == 0x9E || b[0] == 0xB7 || b[2] != 0x30) *addr &= 0x7F;
            return DEVT_THERMO;
        }
        if (b[2] == 0x12) {
            if (b[0] < 0xB0) *addr = b[0]; else if (b[0] == 0xB8) *addr = b[1]; else return -1; /* -1: must NOT create a device */
            if (who == 2) return DEVT_COVER;
            if (who == 1) {
                const char *w = strchr(own + 1, '*') + 1; int what = atoi(w);
                if (!strncmp(w, "1000#", 5)) what = atoi(w + 5);
                if (what >= 2 && what <= 10) return DEVT_DIMMER;
                if (what == 30 || what == 31) return DEVT_DIMMER;
                if (what == 0 || what == 1 || (what >= 11 && what <= 29)) return DEVT_SWITCH;
            }
        }
        return 0;
    }
    if (n == 8 && b[0] == 0xD1) {
        *addr = b[1];
        if ((b[2] & 0x0F) == 0x02 && who == 18) return DEVT_ENERGY;
        if ((b[2] & 0x0F) == 0x03 && who == 4) { if (b[2] != 0x03) *addr &= 0x7F; return DEVT_THERMO; }
        if ((b[2] & 0x0F) == 0x01 && who == 2 && b[4] == 0x09) return DEVT_COVER;
        if ((b[2] & 0x0F) == 0x01 && who == 1 && b[4] == 0x0D && b[5] == 0x0D) return DEVT_DIMMER;
    }
    return 0;
}

int main(int argc, char **argv)
{
    char line[4096]; BYTE body[8]; int n;
    long total = 0, checked = 0, ok = 0, bad = 0;
    if (argc < 2) { fprintf(stderr, "usage: %s corpus.tsv | -\n", argv[0]); return 2; }
    FILE *fp = strcmp(argv[1], "-") ? fopen(argv[1], "r") : stdin;
    if (!fp) { perror(argv[1]); return 2; }
    while (fgets(line, sizeof line, fp)) {
        char *tab, *own = NULL; BYTE addr = 0; int exp, i;
        if (line[0] == '#' || line[0] == '\n') continue;
        tab = strchr(line, '\t'); if (tab) { *tab = 0; own = tab + 1; own[strcspn(own, "\r\n")] = 0; }
        n = hex2bytes(line, body);
        if (n != 4 && n != 8) continue;
        memset(devc, 0xFF, sizeof devc);
        classify(body, n);
        total++;
        if (!own) {           /* translate mode: print the table */
            printf("%s ->", line);
            for (i = 0; i < DEV_NR; i++) if (devc[i].all != 0xFF) printf(" [%02X]=%02X", i, devc[i].devType);
            printf("\n");
            continue;
        }
        exp = expected(body, n, own, &addr);
        if (exp == 0) continue;
        checked++;
        if (exp == -1) {      /* group / area frame: no device may appear */
            int any = 0;
            for (i = 0; i < DEV_NR; i++) if (i != 0xB1 && devc[i].all != 0xFF) any = 1;
            if (!any) ok++; else { bad++; printf("MISMATCH %s %s: group/area frame created a device\n", line, own); }
            continue;
        }
        if (addr == 0 || addr >= DEV_NR) { checked--; continue; }
        if (devc[addr].devType == exp) ok++;
        else { bad++; printf("MISMATCH %s %s: addr %02X expected %02X got %02X\n", line, own, addr, exp, devc[addr].all); }
    }
    if (checked) printf("frames %ld, checked %ld, ok %ld, mismatch %ld\n", total, checked, ok, bad);
    return bad ? 1 : 0;
}
