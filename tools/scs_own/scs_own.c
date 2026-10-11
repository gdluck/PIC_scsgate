/* scs_own.c - SCS -> OpenWebNet translator, C port of scs_own_all.py / scs_own_fw.py. See scs_own.h. */
#include "scs_own.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>

struct exact_row { uint64_t key; uint8_t len; const char *msgs; };
struct other_row { const char *key; const char *msgs; };
#include "scs_own_tables.h"

/* ------------------------------------------------------------------ output helpers */
typedef scs_own_list outbuf;

static void emit(outbuf *o, const char *s)
{
    int i;
    for (i = 0; i < o->n; i++)                       /* keep the first occurrence only (dict.fromkeys) */
        if (!strcmp(o->msg[i], s)) return;
    if (o->n >= SCS_OWN_MAX) return;
    strncpy(o->msg[o->n], s, SCS_OWN_LEN - 1);
    o->msg[o->n][SCS_OWN_LEN - 1] = 0;
    o->n++;
}

static void emitf(outbuf *o, const char *fmt, ...)
{
    char s[SCS_OWN_LEN * 2]; va_list ap;
    va_start(ap, fmt); vsnprintf(s, sizeof s, fmt, ap); va_end(ap);
    emit(o, s);
}

/* space separated message list -> individual messages */
static void emit_list(outbuf *o, const char *list)
{
    char s[SCS_OWN_LEN]; int i = 0;
    for (;; list++) {
        if (*list == ' ' || *list == 0) {
            if (i) { s[i] = 0; emit(o, s); i = 0; }
            if (!*list) return;
        } else if (i < SCS_OWN_LEN - 1) s[i++] = *list;
    }
}

/* emit each message of list with "*OLD" (followed by #, * or ##) replaced by "*NEW" (_sub_where) */
static void emit_list_sub(outbuf *o, const char *list, const char *old, const char *new_)
{
    char s[SCS_OWN_LEN], r[SCS_OWN_LEN * 2]; int i = 0; size_t ol = strlen(old);
    for (;; list++) {
        if (*list == ' ' || *list == 0) {
            if (i) {
                const char *p = s; char *q = r; s[i] = 0;
                while (*p) {
                    if (*p == '*' && !strncmp(p + 1, old, ol) && (p[1 + ol] == '#' || p[1 + ol] == '*')) {
                        *q++ = '*'; strcpy(q, new_); q += strlen(new_); p += 1 + ol;
                    } else *q++ = *p++;
                }
                *q = 0; emit(o, r); i = 0;
            }
            if (!*list) return;
        } else if (i < SCS_OWN_LEN - 1) s[i++] = *list;
    }
}

/* ------------------------------------------------------------------ table lookups */
static const char *exact(const struct exact_row *t, int n, uint64_t key, int len)
{
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int m = (lo + hi) / 2;
        if (t[m].key < key) lo = m + 1;
        else if (t[m].key > key) hi = m - 1;
        else return t[m].len == len ? t[m].msgs : NULL;
    }
    return NULL;
}
static uint64_t key_of(const uint8_t *b, int n) { uint64_t k = 0; int i; for (i = 0; i < n; i++) k = (k << 8) | b[i]; return k; }

static const char *other_lookup(const char *key)
{
    int i;
    for (i = 0; i < N_S_OTHER; i++) if (!strcmp(TBL_S_OTHER[i].key, key)) return TBL_S_OTHER[i].msgs;
    return NULL;
}

/* "who what|who what" entries -> "*who*what*where##" */
static void emit_vals(outbuf *o, const char *entries, const char *where)
{
    char who[8], what[24]; const char *p = entries;
    if (!p) return;
    while (*p) {
        int i = 0;
        while (*p && *p != ' ') who[i++] = *p++;
        who[i] = 0; if (*p) p++;
        i = 0;
        while (*p && *p != '|') what[i++] = *p++;
        what[i] = 0; if (*p) p++;
        emitf(o, "*%s*%s*%s##", who, what, where);
    }
}

/* ------------------------------------------------------------------ helpers */
uint8_t scs_xor(const uint8_t *b, int n) { uint8_t x = 0; int i; for (i = 0; i < n; i++) x ^= b[i]; return x; }

static const char *where_from_addr(uint8_t a, char *buf)
{                               /* '%X%X' when both nibbles < 10, else '%02d%02d' */
    int A = a >> 4, PL = a & 0x0F;
    if (A < 10 && PL < 10) sprintf(buf, "%d%d", A, PL); else sprintf(buf, "%02d%02d", A, PL);
    return buf;
}

/* ================================================================== WHO 4 (bt_termo), scs_own_fw.py */
static int stat_val(uint8_t v)
{
    static const struct { uint8_t b; uint8_t v; } t[] = {
        {0x00, 1}, {0x01, 0}, {0x10, 2}, {0x11, 3}, {0x12, 4}, {0x20, 5}, {0x21, 6}, {0x22, 7}, {0x23, 8}, {0x2F, 9},
        {0x30, 10}, {0x31, 11}, {0x32, 12}, {0x3F, 13}, {0x24, 14}, {0x25, 15}, {0x26, 16}, {0x40, 17}, {0x41, 18},
        {0x42, 19}, {0x43, 20}, {0x44, 21}, {0x45, 22}};
    unsigned i;
    if (v >= 0x80 && v < 0xE5) return 100 + v - 0x80;
    for (i = 0; i < sizeof t / sizeof *t; i++) if (t[i].b == v) return t[i].v;
    return -1;
}
static int mode12(uint8_t v)
{
    static const struct { uint8_t b; int v; } t[] = {
        {0xF0, 1}, {0xF1, 0}, {0xF2, 102}, {0xF3, 202}, {0xFF, 303}, {0x10, 108}, {0x11, 107}, {0x12, 208}, {0x13, 207},
        {0x1B, 408}, {0x1C, 407}, {0x1D, 402}, {0x1E, 410}, {0x1F, 508}, {0x20, 507}, {0x21, 502}, {0x22, 510}};
    unsigned i; for (i = 0; i < sizeof t / sizeof *t; i++) if (t[i].b == v) return t[i].v;
    return -1;
}
static const char *pair05(uint8_t v)
{
    static const struct { uint8_t b; const char *s; } t[] = {
        {0xF0, "1*1"}, {0xF1, "2*1"}, {0xF2, "1*2"}, {0xF3, "2*2"}, {0xF4, "0*2"}, {0xF9, "1*31"}, {0xFA, "1*32"},
        {0xFF, "0*5"}, {0x10, "1*3"}, {0x11, "1*4"}, {0x12, "2*3"}, {0x13, "2*4"}, {0x14, "3*3"}, {0x15, "3*4"},
        {0x16, "3*2"}, {0x17, "3*1"}, {0x18, "0*3"}, {0x19, "0*4"}, {0x1A, "0*1"}};
    unsigned i; for (i = 0; i < sizeof t / sizeof *t; i++) if (t[i].b == v) return t[i].s;
    return NULL;
}
static const char *val0d(uint8_t v)
{
    static const struct { uint8_t b; const char *s; } t[] = {
        {0x00, "00"}, {0x0A, "01"}, {0x14, "02"}, {0x1E, "03"}, {0x80, "4"}, {0x81, "5"}, {0x86, "6"}, {0x82, "7"},
        {0x85, "8"}, {0xF6, "11"}, {0xEC, "12"}, {0xE2, "13"}};
    unsigned i; for (i = 0; i < sizeof t / sizeof *t; i++) if (t[i].b == v) return t[i].s;
    return NULL;
}
static int dims4(uint8_t d)
{
    static const struct { uint8_t b; int v; } t[] = {
        {0x01, 4}, {0x02, 5}, {0x03, 6}, {0x04, 8}, {0x05, 7}, {0x08, 60}, {0x0B, 11}, {0x0C, 2}, {0x0D, 13}, {0x0E, 14},
        {0x0F, 3}, {0x12, 12}, {0x13, 19}, {0x14, 17}, {0x16, 22}, {0x17, 21}, {0x19, 29}, {0x21, 15}};
    unsigned i; for (i = 0; i < sizeof t / sizeof *t; i++) if (t[i].b == d) return t[i].v;
    return -1;
}
static void temp4(uint8_t hi, uint8_t lo, char *buf) { sprintf(buf, "%d%03d", hi >> 4, (hi & 0x0F) * 256 + lo); }
static void where_short4(uint8_t z, int n, const char *zero, char *buf)
{
    if (z >= 0x80) { if (n) sprintf(buf, "%d#%d", z & 0x7F, n); else sprintf(buf, "%d", z); }
    else if (n) sprintf(buf, "%d%02d", n, z);
    else if (z == 0) strcpy(buf, zero);
    else sprintf(buf, "%d", z);
}

static void thermo_short(outbuf *o, uint8_t c, uint8_t z, uint8_t s, uint8_t v)
{
    char w[32]; int n = s & 0x0F;
    if (s >> 4 != 3) return;
    if ((c == 0xB4 || c == 0xB5) && n != 0x0F) {
        if (n) sprintf(w, "%d%02d", n, z); else sprintf(w, "%d", z);
        emitf(o, "*#4*%s*0*%04d##", w, v + (c == 0xB5 ? 256 : 0));
        return;
    }
    if (c == 0xB7 && v >= 0xF0 && mode12(v) >= 0) { emitf(o, "*4*%d*%d##", mode12(v), z); return; }
    if (c >= 0x90 && c <= 0x92) { emitf(o, "*#4*%d*#14*%04d*%d##", z, v * 5, c - 0x8F); return; }
    if ((c == 0x96 || c == 0xB7) && stat_val(v) >= 0) {
        where_short4(z, n, "#0", w);
        emitf(o, "*#4*%s*%s20*%d##", w, c == 0x96 ? "#" : "", stat_val(v));
        return;
    }
    if (c == 0x9D || c == 0x9E) {
        char val[8] = ""; where_short4(z, n, "#0", w);
        if (!(c == 0x9E && v == 0xFF)) sprintf(val, "#%d", v);
        emitf(o, "*4*%s%s*%s##", c == 0x9D ? "4001" : "4002", val, w);
        return;
    }
    if (c == 0x93 && (v == 0x0D || v == 0x0E)) { emitf(o, "*4*%d*%d##", v == 0x0D ? 39 : 40, z); return; }
    if (c == 0x9F || c == 0xBF) {
        int what = v == 0xE0 ? 41 : v == 0xE1 ? 42 : v == 0xE2 ? 43 : v == 0xE5 ? 44 : 0;
        if (what) emitf(o, "*4*%d*%d##", what, z);
    }
}

static void thermo_ext(outbuf *o, const uint8_t *b)
{
    uint8_t h = b[0], z = b[1], a = b[2], s = b[3], dim = b[4], b1 = b[5], b2 = b[6], b3 = b[7];
    static const uint8_t d1dims[] = {0x01, 0x02, 0x04, 0x05, 0x0B, 0x0C, 0x0F, 0x14, 0x16, 0x17, 0x19};
    int d = dims4(dim), n, i, ok = 0; char w[32], dd[8], pre[48], t[16];
    if (d < 0 || (a & 0x0F) != 3) return;
    if (h == 0xD2 && (s & 0x0F) == 4) ok = 1;
    else if (h == 0xD1 && s == 0x02) { for (i = 0; i < 11; i++) if (d1dims[i] == dim) ok = 1; }
    if (!ok) return;
    n = a >> 4;
    if (n && dim != 0x0D && dim != 0x0E && dim != 0x12 && dim != 0x13) sprintf(w, "%d%02d", n, z);
    else if (z == 0) strcpy(w, dim != 0x12 ? "#0" : "0");
    else sprintf(w, "%d", z);
    sprintf(dd, "%s%d", h == 0xD1 ? "#" : "", d);
    sprintf(pre, "*#4*%s*%s*", w, dd);
    switch (dim) {
    case 0x01: case 0x02: case 0x03: case 0x0B: emitf(o, "%s%d##", pre, b1); return;
    case 0x04: pre[strlen(pre) - 1] = 0; emitf(o, "%s#%d*%04d##", pre, b1 + 1, b2 * 5); return;
    case 0x05: {
        const char *p = pair05(b1);
        if (!p) { emit(o, pre); return; }                  /* firmware emits this truncated string */
        if (b2 == 0xFF) {
            if (b1 < 0xF0 || b1 == 0xFF) emitf(o, "%s%s##", pre, p);
            else emitf(o, "%s%c*0##", pre, p[0]);
        } else emitf(o, "%s%s*%04d##", pre, p, b2 * 5);
        return; }
    case 0x08: emitf(o, "%s%d##", pre, b3); return;
    case 0x0C: case 0x0F: if (b1 < 0x20) { temp4(b1, b2, t); emitf(o, "%s%s##", pre, t); } return;
    case 0x0E: if (b1 < 0x20) { temp4(b1, b2, t); emitf(o, "%s%s*3##", pre, t); } return;
    case 0x0D: if (val0d(b1)) emitf(o, "%s%s##", pre, val0d(b1)); return;
    case 0x12:
        if (b2 >= 0x20) return;
        temp4(b2, b3, t); emitf(o, "%s%s*3##", pre, t);
        emitf(o, "*4*%d*%s##", mode12(b1), w);            /* unknown mode prints -1 like the firmware */
        return;
    case 0x13: {
        char s1[8] = "", s2[8] = "";
        if (stat_val(b2) >= 0) sprintf(s1, "%d", stat_val(b2));
        if (stat_val(b1) >= 0) sprintf(s2, "%d", stat_val(b1));
        emitf(o, "%s%s*%s##", pre, s1, s2); return; }
    case 0x14: emitf(o, "%s%d*%d*%04d##", pre, b1, b2, b3 * 5); return;
    case 0x16: {
        char tt[8] = "", lo[4] = "", tail[8] = ""; int hi = b1 >> 4, lon = b1 & 0x0F;
        if (b3 != 0xFF) sprintf(tt, "%04d", b3 * 5);
        if (h == 0xD1) { sprintf(lo, "%d", lon); sprintf(tail, "*%d", hi == 0 ? 1 : hi == 1 ? 0 : hi); }
        else {
            if (lon != 0x0F) sprintf(lo, "%d", lon);
            strcpy(tail, hi == 0 ? "*1" : hi == 1 ? "*0" : hi == 0xF ? "*" : "");
        }
        emitf(o, "*#4*3#%s*%s*%d*%s*%s%s##", w, dd, b2, tt, lo, tail); return; }
    case 0x17: emitf(o, "%s%d*%d*%d##", pre, b1, b2, b3); return;
    case 0x19: if (b1 <= 100 || h == 0xD1) emitf(o, "%s%d*%d*%d##", pre, b1, b2, b3); return;
    case 0x21: {
        int wv = b2 * 256 + b3; char bits[5];
        for (i = 0; i < 4; i++) bits[i] = ((b1 >> 4) >> (3 - i)) & 1 ? '1' : '0';
        bits[4] = 0;
        emitf(o, "%s%d*%d%03d*%s##", pre, b1 & 0x0F, wv >> 15, wv & 0x7FFF, bits); return; }
    }
}

/* ================================================================== CEN / CEN+ (bt_luci) */
static void cen_frame(outbuf *o, uint8_t c, uint8_t a, uint8_t s, uint8_t v)
{
    uint8_t b[4] = {c, a, s, v}; char w[8]; const char *t = exact(TBL_CEN, N_CEN, key_of(b, 4), 4);
    if (t) { emit_list(o, t); return; }
    if (c == 0xCD) {
        where_from_addr(a, w);
        if (s == 0x14) emitf(o, "*15*%02d*%s##", v, w);
        else if (s == 0x10) emitf(o, "*15*%02d#%d*%s##", v & 0x1F, v >> 5, w);
        else if (s == 0x11) emitf(o, "*15*%02d#%d*%s##", v & 0x1F, (v >> 5) + 3, w);
        return;
    }
    if (c == 0xB2 && s >= 0x90 && s <= 0x97) { emitf(o, "*25*%d#%d*2%d##", 21 + s - 0x90, v & 0x1F, a | ((v >> 5) << 8)); return; }
    if (c == 0xB1 && s >= 0x93 && s <= 0x97) {
        switch (s) {
        case 0x93: emitf(o, "*25*11#%d*1%d##", v, a); break;
        case 0x94: emitf(o, "*25*12*1%d##", a); break;
        case 0x95: emitf(o, "*25*13#%d#1*1%d##", v, a); break;
        case 0x96: emitf(o, "*25*14#%d#1*1%d##", v, a); break;
        case 0x97: emitf(o, "*25*15*1%d##", a); break;
        }
        return;
    }
    if (c == 0xB4 && s == 0x90) { if (v < 0x9A) emitf(o, "*#25*3%X##", v); else emitf(o, "*#25*3%d##", v - 54); return; }
    if (c == 0xB4 && (s == 0x91 || s == 0x92) && v <= 1) { emitf(o, "*25*%d#%d*3%X##", 31 + v, s - 0x91, a); return; }
    if (s == 0x10 && v == 0 && (c == 0xB1 || c == 0xB3 || c == 0xB5)) {
        if (c == 0xB1) emit(o, "*14*1*0##"); else if (c == 0xB3) emitf(o, "*14*1*%d##", a); else emitf(o, "*14*1*#%d##", a);
    }
}

/* ================================================================== short frames (WHO 1/2/9/0/14/15/25) */
static void short_frame(outbuf *o, uint8_t c, uint8_t a, uint8_t s, uint8_t v)
{
    char w[16]; int cen_c = (c == 0xCD || c == 0xB2 || c == 0xB1 || c == 0xB4 || c == 0xB3 || c == 0xB5);
    int cen_s = (s == 0x10 || s == 0x11 || s == 0x14 || s == 0x15 || s == 0x04);
    if (s == 0x12) {
        if (c == 0xB8) emit_vals(o, TBL_S_STATUS[v], where_from_addr(a, w));
        else if (c == 0xB1) emit_vals(o, TBL_S_GENERAL[v], "0");
        else if (c == 0xB3) { if (a == 0) strcpy(w, "00"); else sprintf(w, "%d", a); emit_vals(o, TBL_S_AREA[v], w); }
        else if (c == 0xB5) { sprintf(w, "#%d", a); emit_vals(o, TBL_S_GROUP[v], w); }
        else if (c == 0xB2) emit_vals(o, TBL_S_POINT[v], "00");
        else if (c == 0xB4) emit_vals(o, TBL_S_POINT[v], "0153");
        else if (c == 0xCD) emit_vals(o, TBL_S_POINT[v], where_from_addr(a, w));
        else if (c < 0xB0 || c > 0xB8) emit_vals(o, TBL_S_POINT[v], where_from_addr(c, w));
    } else if (cen_c && ((s >> 4) == 9 || cen_s)) cen_frame(o, c, a, s, v);
    if ((s >> 4) == 9 && (c == 0xB0 || c == 0xB1 || c == 0xB3 || c == 0xB5 || c == 0xB8)) {
        uint8_t k[4] = {0xB8, 0x31, s, v}; const char *t = exact(TBL_AUX, N_AUX, key_of(k, 4), 4);
        if (t) emit_list(o, t);
    }
    if (s == 0x12 || (s >> 4) == 9 || (cen_c && cen_s)) return;
    {
        char key[12]; const char *t;
        sprintf(key, "%s%02X%02X", c == 0xB8 ? "B8_" : "31_", s, v);
        where_from_addr(c == 0xB8 ? a : c, w);
        if ((t = other_lookup(key)) != NULL) emit_list_sub(o, t, "31", w);
        else if (c == 0xB8 && s == 0x17 && (v >> 6) != 2) emitf(o, "*0*%d*%s##", v, w);
        else if (c == 0xB8 && s == 0x1C) {
            int hi = v >> 5, n = v & 0x1F; char sfx[8] = "";
            if (n) sprintf(sfx, "#%d", n);
            if (v == 0xFF) emitf(o, "*0*43*%s##", w);
            else if (hi == 0) emitf(o, "*0*42*%s##", w);
            else if (hi == 1) emitf(o, "*0*42%s*%s##", sfx, w);
            else if (hi == 2) emitf(o, "*0*40%s*%s##", sfx, w);
            else if (hi == 3) emitf(o, "*0*41%s*%s##", sfx, w);
            else if (hi == 4) { emitf(o, "*0*%d*%s##", n == 0 ? 41 : 40, w); emitf(o, "*0*44*%s##", w); }
            else if (hi == 5) emitf(o, "*0*46%s*%s##", sfx, w);
            else if (hi == 6) emitf(o, "*0*45*%s##", w);
        }
    }
}

/* ================================================================== extended frames */
static int ldim(uint8_t code)
{
    switch (code) { case 0x06: return 2; case 0x0C: return 12; case 0x10: return 6; case 0x15: return 5; case 0x16: return 7; case 0x17: return 8; }
    return 0;
}

static void light_dim_frame(outbuf *o, const uint8_t *b)
{
    uint8_t aa = b[1], bb = b[2], cmd = b[3]; int dim = ldim(b[4]), i = bb >> 4, status = (cmd & 0x0F) == 4;
    char w[24], ifs[8] = "", val[32], tmp[8];
    if (i) sprintf(ifs, "#4#%02d", i);
    if ((status && dim == 5) || (bb & 0x0F) != 1 || (b[0] == 0xD5 && i > 2)) return;
    if (b[0] == 0xD1) sprintf(w, "%s%s", where_from_addr(aa, tmp), ifs);
    else if (b[0] == 0xD2) {
        if (aa == 0) { if (i) sprintf(w, "00%s", ifs); else strcpy(w, "0"); }
        else sprintf(w, "%s%s", where_from_addr(aa, tmp), ifs);
    } else {
        if (status && dim == 12) return;
        if (bb == 0x01) sprintf(w, "#%d", aa);
        else if (i == 2) {
            if (cmd == 0x32 || (aa & 0x0F) || dim == 12) return;
            if (aa >> 4) sprintf(w, "0#4#%02d", aa >> 4); else strcpy(w, "0");
        } else if (cmd == 0x32) sprintf(w, "%02d", aa);
        else { if (aa >> 4) sprintf(w, "%d#4#%02d", aa & 0x0F, aa >> 4); else sprintf(w, "%d", aa & 0x0F); }
    }
    if (dim == 12) sprintf(val, "%d*%d*%d", b[5] + ((status && (b[6] & 0x80)) ? 256 : 0), b[6] & 0x7F, b[7]);
    else if (dim == 2 || dim == 7) sprintf(val, "%d*%d*%d", b[5], b[6], b[7]);
    else if (dim == 5 || dim == 6) sprintf(val, "%d", ((b[5] & 0x0F) << 16) | (b[6] << 8) | b[7]);
    else sprintf(val, "%d", (b[5] << 16) | (b[6] << 8) | b[7]);
    emitf(o, "*#1*%s*%s%d*%s##", w, (cmd & 0x0F) == 2 ? "#" : "", dim, val);
}

static void cover_adv_frame(outbuf *o, const uint8_t *b)
{
    static const char *adv[16] = {"10", "11", "12", "#11", "14", "13", NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, "#13"};
    uint8_t aa = b[1], bb = b[2], cmd = b[3], x = b[5]; const char *what = adv[x >> 4];
    int hi = x >> 4, q = (x >> 3) & 1, i = bb >> 4; char ppp[4], w[24], ifs[8] = "", tmp[8], body[32];
    (void)hi;
    if (!what) return;
    sprintf(ppp, "%d%d%d", (x >> 2) & 1, (x >> 1) & 1, x & 1);
    if (i) sprintf(ifs, "#4#%02d", i);
    if (b[0] == 0xD1) sprintf(w, "%s%s", where_from_addr(aa, tmp), ifs);
    else if (b[0] == 0xD2) {
        if (aa == 0) { if (i > 1) sprintf(w, "0#4#%02d", i - 1); else strcpy(w, "0"); }
        else sprintf(w, "%s%s", where_from_addr(aa, tmp), ifs);
    } else {
        if (bb == 0x01) sprintf(w, "#%d", aa);
        else if (i == 2) sprintf(w, "0#4#%02d", aa >> 4);
        else if (i == 1 && (aa >> 4) == 0) { if (aa == 0) strcpy(w, "00"); else sprintf(w, "%d", aa); }
        else if ((aa & 0x0F) < 10) sprintf(w, "#%d#4#%02d", aa & 0x0F, aa >> 4);
        else sprintf(w, "#4#%02d", aa >> 4);
    }
    if (cmd == 0x44) { if (what[0] != '#') emitf(o, "*#2*%s*10*%s*%d*%s*%d##", w, what, b[6], ppp, b[7] >> 4); return; }
    if (!strcmp(what, "#11")) { emitf(o, "*#2*%s*#11#%s#%d*%d##", w, ppp, q, b[6]); return; }
    if (!strcmp(what, "#13")) { emitf(o, "*#2*%s*#13#%d*%s##", w, q, ppp); return; }
    if (!strcmp(what, "11") || !strcmp(what, "12")) sprintf(body, "%s#%d#%s#%d", what, b[6], ppp, q);
    else sprintf(body, "%s#%s#%d", what, ppp, q);
    emitf(o, "*2*%s%s*%s##", b[0] == 0xD1 ? "1000#" : "", body, w);
}

/* bt_device clock broadcasts: bytes read as text, decimal prefix of the two hex digits ('2A' -> 2, 'AB' -> 0) */
static int dec2(uint8_t x)
{
    int hi = x >> 4, lo = x & 0x0F;
    if (hi > 9) return 0;
    return lo > 9 ? hi : hi * 10 + lo;
}
static void clock_frame(outbuf *o, const uint8_t *b)
{
    if ((b[3] & 0x0F) == 6) {
        char tz[8] = "";
        if ((b[7] & 0x0F) != 0x0F) sprintf(tz, "%d%02d", (b[7] >> 4) & 1, b[7] & 0x0F);
        emitf(o, "*#13**#0*%02d*%02d*%02d*%s##", dec2(b[4]), dec2(b[5]), dec2(b[6]), tz);
    } else {
        int day, w;
        /* note: bt_device itself drops frames with dd == 0x28 (firmware quirk); we still decode them */
        day = dec2(b[4]) < 40 ? dec2(b[4]) : 0;
        w = (b[5] >> 4) == 0xF ? 0 : b[5] >> 4;
        emitf(o, "*#13**#1*%02d*%02d*%02d*%02d%02d##", w, day, b[5] & 0x0F, dec2(b[6]), dec2(b[7]));
    }
}

/* ================================================================== requests the gateway itself sends (gw_inverse.py) */
static int lreq(uint8_t d, uint8_t v)
{
    if (d == 0x0D && v == 0x0D) return 1;
    if (v) return 0;
    switch (d) { case 0x06: return 2; case 0x0D: return 4; case 0x15: return 5; case 0x10: return 6; case 0x16: return 7;
                 case 0x17: return 8; case 0x0C: return 12; case 0x0B: return 14; case 0x07: return 15; }
    return 0;
}
static int treq99(uint8_t v)
{
    switch (v) { case 0x00: return 0; case 0x0C: return 2; case 0x0F: return 3; case 0x0B: return 11; case 0x12: return 12; case 0x0D: return 13;
                 case 0x0E: return 14; case 0x90: return 16; case 0x14: return 17; case 0x13: return 19; case 0x10: return 20; case 0xF1: return 27;
                 case 0xF2: return 28; case 0xC3: return 30; case 0xC4: return 31; case 0xC5: return 32; }
    return -1;
}
static int treqd1(uint8_t d)
{
    switch (d) { case 0x21: return 15; case 0xCD: return 18; case 0x17: return 21; case 0x19: return 29; case 0x08: return 60;
                 case 0x01: return 4; case 0x02: return 5; case 0x03: return 6; case 0x05: return 7; }
    return -1;
}
static int thermo_where(uint8_t z, int n, char *w)
{
    if (z >= 0x80) { if (!n) return 0; sprintf(w, "%d#%d", z & 0x7F, n); return 1; }
    if (n) sprintf(w, "%d%02d", n, z); else sprintf(w, "%d", z);
    return 1;
}
static void gateway_own(outbuf *o, const uint8_t *b, int len)
{
    const char *t = exact(TBL_INV, N_INV, key_of(b, len), len); char w[24];
    if (t) { emit_list(o, t); return; }
    if (len == 4) {
        uint8_t c = b[0], a = b[1], s = b[2], v = b[3];
        if (s == 0x15 && v == 0) {                               /* WHO 1 / 2 status request (same frame for both) */
            if (c < 0xB0) emitf(o, "*#1*%s##", where_from_addr(c, w));
            else if (c == 0xB1 && a == 0) emit(o, "*#1*0##");
            else if (c == 0xB3) emitf(o, "*#1*%d##", a);
            else if (c == 0xB5) emitf(o, "*#1*#%d##", a);
            return;
        }
        if (c == 0x99 && (s >> 4) == 3) {                        /* WHO 4 requests */
            int n = s & 0x0F;
            if (v == 0xC0 && a < 0x80) { if (a) emitf(o, "*#4*#0#%d##", a); else emit(o, "*#4*#0##"); return; }
            if (treq99(v) >= 0 && thermo_where(a, n, w)) emitf(o, "*#4*%s*%d##", w, treq99(v));
            return;
        }
        if (c == 0xA9 && s == 0x30 && v == 0x10) { emitf(o, "*#4*%d*20##", a); return; }
        if (c == 0xB9 && a == 0 && s == 0x30 && v == 0x10) emit(o, "*#4*#0*20##");
        return;
    }
    {
        uint8_t h = b[0], aa = b[1], bb = b[2], cmd = b[3], d = b[4], v1 = b[5], v2 = b[6], v3 = b[7];
        if ((h == 0xD1 || h == 0xD2 || h == 0xD5) && cmd == 0x43 && lreq(d, v1) && !v2 && !v3 && (bb & 0x0F) == 1) {
            int dim = lreq(d, v1), i = bb >> 4; char ifs[8] = "", tmp[8];
            if (i) sprintf(ifs, "#4#%02d", i);
            if (h == 0xD1) sprintf(w, "%s%s", where_from_addr(aa, tmp), ifs);
            else if (h == 0xD2) { if (aa) return; sprintf(w, "0%s", ifs); }
            else {
                if (bb & 0x10) sprintf(w, "%d", aa & 0x0F); else sprintf(w, "#%d", aa & 0x0F);
                if (aa >> 4) sprintf(w + strlen(w), "#4#%02d", aa >> 4);
            }
            emitf(o, "*#1*%s*%d##", w, dim);
            return;
        }
        if (h == 0xD1 && cmd == 0x03 && (bb & 0x0F) == 3 && treqd1(d) >= 0 && !v1 && !v2 && !v3) {
            if (thermo_where(aa, bb >> 4, w)) emitf(o, "*#4*%s*%d##", w, treqd1(d));
            return;
        }
        if (h == 0xD2 && aa == 0 && bb == 0x03 && cmd == 0x03 && treqd1(d) >= 0 && !v1 && !v2 && !v3) { emitf(o, "*#4*0*%d##", treqd1(d)); return; }
        if (h == 0xD1 && aa == 0 && bb == 0x03 && cmd == 0x03 && d == 0xC2 && !v2 && !v3) emitf(o, "*#4*#%d##", v1);
    }
}

static void ext_frame(outbuf *o, const uint8_t *b)
{
    uint64_t key = key_of(b, 8); const char *t; char w[8];
    if ((t = exact(TBL_EXT, N_EXT, key, 8)) != NULL) { emit_list(o, t); return; }
    if ((t = exact(TBL_ENERGY, N_ENERGY, key, 8)) != NULL) { emit_list(o, t); return; }
    if ((b[0] == 0xD1 || b[0] == 0xD2 || b[0] == 0xD5) && (b[2] == 0x01 || b[2] == 0x11) &&
        (b[3] == 0x42 || b[3] == 0x43 || b[3] == 0x44 || b[3] == 0x32 || b[3] == 0x34)) {
        uint8_t k[8]; memcpy(k, b, 8); k[1] = 0x31;
        if ((t = exact(TBL_EXT, N_EXT, key_of(k, 8), 8)) != NULL) { emit_list_sub(o, t, "31", where_from_addr(b[1], w)); return; }
    }
    if ((b[0] == 0xD1 || b[0] == 0xD2) && (b[2] & 0x0F) == 1 && b[4] == 0x0D && (b[3] == 0x34 || b[3] == 0x44 || b[3] == 0x32) &&
        (b[5] == 0x0D || b[5] == 0x01 || b[5] == 0x00 || b[5] == 0x10)) {
        /* bt_luci dimmer level frames: x=0D -> dim 1 level 100+lv; x=01 -> dim 4 level 100; x=00 (D1 only)/10 -> dim 4 level 100+lv */
        char ww[24], tmp[8]; uint8_t x = b[5], lv = b[6], sp = b[7];
        if (b[2] >> 4) sprintf(ww, "%s#4#%02d", where_from_addr(b[1], tmp), b[2] >> 4); else where_from_addr(b[1], ww);
        if (b[3] == 0x32) { if (x == 0x01) emitf(o, "*1*1000#0#4*%s##", ww); return; }
        if (x == 0x00 && b[0] != 0xD1) return;
        if (lv == 0 && sp == 0) emitf(o, "*1*0*%s##", ww);
        else emitf(o, "*#1*%s*%d*%d*%d##", ww, x == 0x0D ? 1 : 4, x == 0x01 ? 100 : 100 + lv, sp);
        return;
    }
    if (b[0] == 0xD2 && b[2] == 0x09 && ((b[3] & 0x0F) == 6 || (b[3] & 0x0F) == 7)) { clock_frame(o, b); return; }
    if ((b[0] == 0xD1 || b[0] == 0xD2 || b[0] == 0xD5) && (b[3] == 0x32 || b[3] == 0x34 || b[3] == 0x42 || b[3] == 0x44) && ldim(b[4])) {
        light_dim_frame(o, b); return;
    }
    if ((b[0] == 0xD1 || b[0] == 0xD2 || b[0] == 0xD5) && (b[3] == 0x32 || b[3] == 0x42 || b[3] == 0x44) && b[4] == 0x09 && (b[2] & 0x0F) == 1) {
        cover_adv_frame(o, b); return;
    }
    if (b[0] == 0xD2 && b[2] == 0x02 && (b[3] >> 4) == 3 && (b[1] >> 4) == 0xA) {
        uint8_t k[8]; memcpy(k, b, 8); k[1] = 0xA1;
        if ((t = exact(TBL_ENERGY, N_ENERGY, key_of(k, 8), 8)) != NULL) { sprintf(w, "5%d", b[1] & 0x0F); emit_list_sub(o, t, "51", w); }
    }
}

/* ================================================================== public API */
int scs_to_own(const uint8_t *body, int len, scs_own_list *o)
{
    const char *t;
    o->n = 0;
    if (len != 4 && len != 8) return 0;
    if (len == 4) thermo_short(o, body[0], body[1], body[2], body[3]); else thermo_ext(o, body);
    if ((t = exact(TBL_MISC, N_MISC, key_of(body, len), len)) != NULL) emit_list(o, t);
    if (len == 4) short_frame(o, body[0], body[1], body[2], body[3]); else ext_frame(o, body);
    if (o->n == 0) gateway_own(o, body, len);
    return o->n;
}

static int hexbytes(const char *hex, uint8_t *b, int max)
{
    int n = 0, hi = -1;
    for (; *hex; hex++) {
        int d = (*hex >= '0' && *hex <= '9') ? *hex - '0' : (*hex >= 'A' && *hex <= 'F') ? *hex - 'A' + 10 :
                (*hex >= 'a' && *hex <= 'f') ? *hex - 'a' + 10 : -1;
        if (d < 0) continue;
        if (hi < 0) hi = d; else { if (n < max) b[n++] = hi * 16 + d; hi = -1; }
    }
    return n;
}

int scs_parse_hex(const char *line, uint8_t *body, int max)
{
    uint8_t b[32]; const char *p = strstr(line, "]:"); int n;
    n = hexbytes(p ? p + 2 : line, b, 32);
    if ((n == 7 || n == 11) && (b[0] == 0xA8 || b[0] == 0xB8 || b[0] == 0xD4) && b[n - 1] == 0xA3) { memmove(b, b + 1, n - 3); n -= 3; }
    else if ((n == 5 || n == 9) && scs_xor(b, n - 1) == b[n - 1]) n--;
    if ((n != 4 && n != 8) || n > max) return -1;
    memcpy(body, b, n);
    return n;
}

int scs_frame_checksum_ok(const char *line)
{
    uint8_t b[32]; const char *p = strstr(line, "]:"); int n = hexbytes(p ? p + 2 : line, b, 32);
    if (n < 4 || !(b[0] == 0xA8 || b[0] == 0xD4) || b[n - 1] != 0xA3) return -1;
    return scs_xor(b + 1, n - 3) == b[n - 2];
}

int scs_hex_to_own(const char *hex, char *buf, int bufsz)
{
    uint8_t body[8]; scs_own_list out; int n = scs_parse_hex(hex, body, 8), k, i, p = 0;
    buf[0] = 0;
    if (n <= 0) return 0;
    k = scs_to_own(body, n, &out);
    for (i = 0; i < k; i++) p += snprintf(buf + p, p < bufsz ? bufsz - p : 0, "%s%s", i ? " + " : "", out.msg[i]);
    return k;
}

#ifdef SCS_OWN_MAIN
/* test driver:  scs_own_test <corpus.tsv>   (BODYHEX \t msg msg ...)   or   scs_own_test - < frames */
int main(int argc, char **argv)
{
    char line[4096], buf[2048]; FILE *f = argc > 1 && strcmp(argv[1], "-") ? fopen(argv[1], "r") : stdin;
    long ok = 0, n = 0;
    if (!f) { perror(argv[1]); return 1; }
    while (fgets(line, sizeof line, f)) {
        char *tab = strchr(line, '\t'), *nl = strchr(line, '\n'); if (nl) *nl = 0;
        if (line[0] == '#') continue;
        if (tab) {                                     /* compare mode */
            char exp[2048], *p = tab + 1, *q = exp; *tab = 0;
            while (*p) { if (*p == ' ') { strcpy(q, " + "); q += 3; p++; } else *q++ = *p++; } *q = 0;
            scs_hex_to_own(line, buf, sizeof buf); n++;
            if (!strcmp(buf, exp)) ok++; else printf("MISMATCH %s\n  exp %s\n  got %s\n", line, exp, buf);
        } else { scs_hex_to_own(line, buf, sizeof buf); printf("%s -> %s\n", line, buf[0] ? buf : "(no translation)"); }
    }
    if (n) printf("%ld/%ld\n", ok, n);
    return ok == n ? 0 : 2;
}
#endif
