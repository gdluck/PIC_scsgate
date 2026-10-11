/* Host-side replay of the PIC_scsgate device-table classifier (OutputMapping) against the
 * firmware corpus.  Build:  make   (needs classifier.inc / covers.inc, produced by extract.py from ESPSCSGATE.C)
 *
 * Usage: ./devtab_test hex2own_corpus.tsv      -> checks every frame, prints mismatches and totals
 *        echo B8311200 | ./devtab_test -       -> prints the device table entry a frame produces
 *
 * The expectation for each frame is derived from the OpenWebNet text the firmware emitted for it
 * (second column of the corpus), never from the classifier's own rules:
 *   WHO 1 WHAT 0/1/11..29 -> switch, WHAT 2..10/30/31 -> dimmer, WHO 2 -> cover, WHAT 255 -> no type;
 *   WHO 4 -> heating zone taken from the WHERE field (Z, Z#N, NZZ probe forms), zones 1..99 only;
 *   WHO 18 -> energy meter 5N; group / area / general / request frames must not create a device.
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
#define DEVT_ZONE_MAX 99

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
int acks = 0, totale_calls = 0;
void queueWrite(char len) { (void)len; acks++; }
void CmdTotaleTapparelle(BYTE c) { (void)c; totale_calls++; }
#include "covers.inc"

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

/* zone number from a WHO 4 WHERE field as bt_termo prints it: "40", "0#3" (zone#actuator), "140" (probe N=1 of
 * zone 40), "1128" (probe 1 of zone 128), "3#40" (dimension 22 rendering).  n = probe/actuator index of the frame.
 * Returns -1 for the central unit forms ("#0", "#0#2", "0#4#01"). */
static int zone_from_where(const char *where, int n)
{
    char buf[32]; char *h;
    if (where[0] == '#') return -1;
    strncpy(buf, where, sizeof buf - 1); buf[sizeof buf - 1] = 0;
    if (!strncmp(buf, "3#", 2)) memmove(buf, buf + 2, strlen(buf + 2) + 1);
    h = strchr(buf, '#');
    if (h) { *h = 0; return atoi(buf); }
    if (n != 0) {
        char pre[8]; sprintf(pre, "%d", n);
        if (strncmp(buf, pre, strlen(pre)) || strlen(buf) <= strlen(pre)) return -2;   /* not a probe form */
        return atoi(buf + strlen(pre));
    }
    return atoi(buf);
}

/* WHERE field of an OpenWebNet message: *WHO*WHAT*WHERE## or *#WHO*WHERE*... */
static void own_fields(const char *own, int *who, char *what, char *where)
{
    const char *p = own + 1; const char *q; size_t l;
    what[0] = where[0] = 0;
    if (*p == '#') p++;
    *who = atoi(p);
    q = strchr(p, '*'); if (!q) return; q++;
    if (own[1] == '#') { l = strcspn(q, "*#"); if (q[l] == '#' && l == 0) l = strcspn(q, "*"); else l = strcspn(q, "*"); strncpy(where, q, l); where[l] = 0; return; }
    l = strcspn(q, "*"); strncpy(what, q, l); what[l] = 0; q += l; if (*q == '*') q++;
    l = strcspn(q, "*"); strncpy(where, q, l); where[l] = 0;
    while (l > 0 && where[l - 1] == '#') where[--l] = 0;       /* trailing ## of a command */
}

/* expected type from the OWN messages the firmware emits for the frame.
 * 0 = no expectation, -1 = no device may be created, otherwise the type at *addr */
static int expected(const BYTE *b, int n, const char *own, BYTE *addr)
{
    int who; char what[64], where[64]; int z;
    own_fields(own, &who, what, where);
    if (n == 4) {
        if ((b[2] & 0xF0) == 0x30 && who == 4) {           /* heating: zone in byte 1 */
            int src_ok = (b[0] >= 0x90 && b[0] <= 0x93) || b[0] == 0x96 || b[0] == 0x9D || b[0] == 0x9E || b[0] == 0x9F
                      || b[0] == 0xB4 || b[0] == 0xB5 || b[0] == 0xB7 || b[0] == 0xBF;
            if (!src_ok) return -1;                            /* 99 / A6 / A9 requests, B6 / B9 central unit forms */
            /* bt_termo ignores N in the set point / mode writes 90..93 ("40"), elsewhere N is a probe index ("140") */
            z = zone_from_where(where, (b[0] >= 0x90 && b[0] <= 0x93) ? 0 : (b[2] & 0x0F));
            if (z == -2) return 0;
            if (z <= 0 || z > DEVT_ZONE_MAX) return -1;
            *addr = (BYTE)z;
            return DEVT_THERMO;
        }
        if (b[2] == 0x12) {
            if (b[0] < 0xB0) *addr = b[0]; else if (b[0] == 0xB8) *addr = b[1]; else return -1; /* B1/B2/B3/B4/B5/BB: no device */
            if (who == 2) return DEVT_COVER;
            if (who == 1) {
                int w = atoi(what);
                if (!strncmp(what, "1000#", 5)) w = atoi(what + 5);
                if (w >= 2 && w <= 10) return DEVT_DIMMER;
                if (w == 30 || w == 31) return DEVT_DIMMER;
                if (w == 0 || w == 1 || (w >= 11 && w <= 29)) return DEVT_SWITCH;
                if (w == 255 && b[0] == 0xB8) return -1;      /* unknown status: says nothing about the type */
            }
        }
        return 0;
    }
    if (n == 8) {
        int kk = b[3] & 0x0F, sys = b[2] & 0x0F;
        if (b[0] == 0xD5) return (who == 1 || who == 2 || who == 4 || who == 18) ? -1 : 0;   /* area / group */
        if (b[0] != 0xD1 && b[0] != 0xD2) return 0;
        if (kk == 0x03) return (who == 1 || who == 2 || who == 4 || who == 18) ? -1 : 0;     /* requests */
        if (kk != 0x02 && kk != 0x04) return 0;
        if (sys == 0x03 && who == 4) {
            if (b[4] == 0xC1 || b[4] == 0xC2) return -1;         /* central unit forms #0#N / #N: the address is not a zone */
            if (where[0] == '#') return 0;                       /* "#0#2" for C4/C5 etc.: configuration dependent rendering */
            z = zone_from_where(where, b[2] >> 4);
            if (z == -2) return 0;
            if (z <= 0 || z > DEVT_ZONE_MAX) return -1;
            *addr = (BYTE)z;
            return DEVT_THERMO;
        }
        if (sys == 0x02 && who == 18) {
            char w5[8];
            if ((b[1] & 0xF0) != 0xA0 || (b[1] & 0x0F) == 0) return -1;
            sprintf(w5, "5%d", b[1] & 0x0F);
            if (strcmp(where, w5)) return 0;                     /* other renderings (749#-5 ...): no expectation */
            *addr = b[1];
            return DEVT_ENERGY;
        }
        if (sys == 0x01 && (who == 1 || who == 2)) {
            if (b[1] == 0 || b[1] >= 0xB0) return -1;
            *addr = b[1];
            if (who == 2 && b[4] == 0x09) return DEVT_COVER;
            if (who == 1 && b[4] == 0x0D && b[5] == 0x0D) return DEVT_DIMMER;
        }
    }
    return 0;
}

/* area cover commands (B3 0A 12 08/09/0A) must move only the tracked covers of that area */
static int cover_area_test(void)
{
    static const BYTE up3[4] = {0xB3, 0x03, 0x12, 0x08}, down4[4] = {0xB3, 0x04, 0x12, 0x09}, stop3[4] = {0xB3, 0x03, 0x12, 0x0A};
    static const BYTE all_up[4] = {0xB1, 0x00, 0x12, 0x08}, grp[4] = {0xB5, 0x03, 0x12, 0x08};
    int bad = 0, i;
    memset(devc, 0xFF, sizeof devc);
    opt.tapparelle_pct = 1; maxtapp = 3;
    devicetappa[0].device = 0x31; devicetappa[1].device = 0x3A; devicetappa[2].device = 0x45;
    for (i = 0; i < 3; i++) { tapparella[i].direction.Val = 0; tapparella[i].request = 0; }
    classify(up3, 4);
    if (tapparella[0].direction.Val != UP || tapparella[1].direction.Val != UP || tapparella[2].direction.Val != 0) bad++;
    classify(down4, 4);
    if (tapparella[2].direction.Val != DOWN || tapparella[0].direction.Val != UP) bad++;
    classify(stop3, 4);
    if (tapparella[0].direction.half.LS != 0 || tapparella[1].direction.half.LS != 0 || tapparella[0].request != 0xFFFF || tapparella[2].direction.Val != DOWN) bad++;
    classify(all_up, 4);
    if (totale_calls != 1) bad++;                         /* general command still goes through CmdTotaleTapparelle */
    classify(grp, 4);
    if (tapparella[0].direction.half.LS != 0) bad++;      /* group membership is unknown: nothing moves */
    for (i = 0; i < DEV_NR; i++) if (i != 0xB1 && devc[i].all != 0xFF) bad++;   /* no device entry from B1/B3/B5 */
    opt.tapparelle_pct = 0; maxtapp = 0;
    printf("cover area test: %s\n", bad ? "FAILED" : "ok");
    return bad;
}

int main(int argc, char **argv)
{
    char line[4096]; BYTE body[8]; int n;
    long total = 0, checked = 0, ok = 0, bad = 0;
    if (argc < 2) { fprintf(stderr, "usage: %s corpus.tsv | -\n", argv[0]); return 2; }
    FILE *fp = strcmp(argv[1], "-") ? fopen(argv[1], "r") : stdin;
    if (!fp) { perror(argv[1]); return 2; }
    if (fp != stdin) bad += cover_area_test();
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
        if (exp == -1) {      /* group / area / request frame: no device may appear */
            int any = 0;
            for (i = 0; i < DEV_NR; i++) if (i != 0xB1 && devc[i].all != 0xFF) any = 1;
            if (!any) ok++; else { bad++; printf("MISMATCH %s %s: frame must not create a device\n", line, own); }
            continue;
        }
        if (addr == 0 || addr >= DEV_NR) { checked--; continue; }
        if (devc[addr].devType == exp) ok++;
        else { bad++; printf("MISMATCH %s %s: addr %02X expected %02X got %02X\n", line, own, addr, exp, devc[addr].all); }
    }
    if (checked) printf("frames %ld, checked %ld, ok %ld, mismatch %ld\n", total, checked, ok, bad);
    return bad ? 1 : 0;
}
