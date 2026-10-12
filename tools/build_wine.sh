#!/bin/sh
# Builds BIN/espscsgate_RASPY_8.hex with the MPLAB 8 command-line tools running under Wine
# (macOS or Linux), the same steps as tools/build_mplab8.bat but without cmd.exe.
#   MPASM:  /dRASPBERRY_8          C18: -D_RASPBERRY_8 -Ou- -Ot- -Ob- -Op- -Or- -Od- -Opa-
#   MPLINK: LIB/18F26K80_B.LKR, /u_CRUNTIME, C18 lib directory
# Needs MPLAB IDE 8.92 (MPASM Suite) and MPLAB C18 v3.4x lite installed in the Wine prefix.
# Run from the repository root:   tools/build_wine.sh
# Environment (all optional):
#   WINE        wine executable (default: wine)
#   WINEPREFIX  the prefix holding the Microchip tools (default: ~/.wine)
#   MPASM_DIR   Unix path of the "MPASM Suite" directory
#   MCC18_DIR   Unix path of the C18 directory (the one holding bin/, h/, lib/)
set -e
WINE=${WINE:-wine}
PREFIX=${WINEPREFIX:-$HOME/.wine}
if [ ! -f ESPSCSGATE.C ] || [ ! -f LIB/18F26K80_B.LKR ]; then
    echo "run this from the repository root (ESPSCSGATE.C not found)" >&2; exit 2
fi
find_one() {  # find_one <glob...> : first existing path
    for p in "$@"; do [ -e "$p" ] && { echo "$p"; return 0; }; done; return 1
}
if [ -z "$MPASM_DIR" ]; then
    MPASM_DIR=$(find_one "$PREFIX"/drive_c/Program*Files*/Microchip/MPASM*Suite "$PREFIX"/drive_c/Program*Files/Microchip/MPASM*Suite) || {
        echo "MPASM Suite not found under $PREFIX/drive_c; set MPASM_DIR" >&2; exit 2; }
fi
if [ -z "$MCC18_DIR" ]; then
    MCC18_DIR=$(find_one "$PREFIX"/drive_c/Program*Files*/Microchip/mplabc18/v3.4? "$PREFIX"/drive_c/MCC18 "$PREFIX"/drive_c/mcc18) || {
        echo "MPLAB C18 not found under $PREFIX/drive_c; set MCC18_DIR" >&2; exit 2; }
fi
for f in "$MPASM_DIR/MPASMWIN.exe" "$MPASM_DIR/MPLink.exe" "$MCC18_DIR/bin/mcc18.exe" "$MCC18_DIR/h/p18cxxx.h" "$MCC18_DIR/lib/clib.lib"; do
    [ -f "$f" ] || { echo "missing: $f" >&2; exit 2; }
done
export WINEPREFIX="$PREFIX"
export WINEDEBUG=${WINEDEBUG:--all}
export WINEDLLOVERRIDES=${WINEDLLOVERRIDES:-mscoree=d;mshtml=d}
MPASM_W=$("$WINE" winepath -w "$MPASM_DIR" | tr -d '\r')
MCC18_W=$("$WINE" winepath -w "$MCC18_DIR" | tr -d '\r')
echo "MPASM Suite: $MPASM_W"
echo "MPLAB C18:   $MCC18_W"
mkdir -p OBJ BIN
rm -f OBJ/*.o OBJ/*.err BIN/espscsgate_RASPY_8.hex BIN/espscsgate_RASPY_8.cof BIN/espscsgate_RASPY_8.map
CFLAGS="-p=18F26K80 -D_RASPBERRY_8 -I. -ILIB -I$MCC18_W\\h -Ou- -Ot- -Ob- -Op- -Or- -Od- -Opa-"
asm() {  # asm <name>
    "$WINE" "$MPASM_DIR/MPASMWIN.exe" /q /p18F26K80 "LIB\\$1.ASM" "/lOBJ\\$1.lst" "/eOBJ\\$1.err" "/oOBJ\\$1.o" /dRASPBERRY_8 || {
        echo "MPASM failed on $1:" >&2; cat "OBJ/$1.err" >&2; exit 1; }
    [ -f "OBJ/$1.o" ] || { echo "MPASM produced no OBJ/$1.o:" >&2; cat "OBJ/$1.err" >&2; exit 1; }
}
cc() {  # cc <source> <name>
    "$WINE" "$MCC18_DIR/bin/mcc18.exe" "$1" "-fo=OBJ\\$2.o" "-fe=OBJ\\$2.err" $CFLAGS || {
        echo "mcc18 failed on $1:" >&2; cat "OBJ/$2.err" >&2; exit 1; }
    [ -f "OBJ/$2.o" ] || { echo "mcc18 produced no OBJ/$2.o:" >&2; cat "OBJ/$2.err" >&2; exit 1; }
}
asm SCS_UART
asm CANREPRO_232_EVO
cc ESPSCSGATE.C ESPSCSGATE
cc 'LIB\DELAY.c' DELAY
"$WINE" "$MPASM_DIR/MPLink.exe" /p18F26K80 "/l$MCC18_W\\lib" /kLIB 'LIB\18F26K80_B.LKR' \
    'OBJ\ESPSCSGATE.o' 'OBJ\CANREPRO_232_EVO.o' 'OBJ\DELAY.o' 'OBJ\SCS_UART.o' \
    /u_CRUNTIME /z__MPLAB_BUILD=1 '/mBIN\espscsgate_RASPY_8.map' /w '/oBIN\espscsgate_RASPY_8.cof' || {
        echo "MPLINK failed" >&2; exit 1; }
[ -f BIN/espscsgate_RASPY_8.hex ] || { echo "MPLINK produced no BIN/espscsgate_RASPY_8.hex" >&2; exit 1; }
echo "build OK: BIN/espscsgate_RASPY_8.hex ($(wc -l < BIN/espscsgate_RASPY_8.hex | tr -d ' ') records)"
