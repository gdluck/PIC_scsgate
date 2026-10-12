@echo off
rem Builds BIN\espscsgate_RASPY_8.hex with the MPLAB 8 command line tools, mirroring espscsgate_RASPY_8.mcp
rem (MPASM: /dRASPBERRY_8; C18: -D_RASPBERRY_8 -Ou- -Ot- -Ob- -Op- -Or- -Od- -Opa-; linker LIB\18F26K80_B.LKR).
rem Needs MPLAB IDE 8.92 (MPASM + MPLINK) and MPLAB C18 v3.4x (the free "lite" edition is enough).
rem Run from the repository root. Under Wine (macOS / Linux):  wine cmd /c tools\build_mplab8.bat
rem Set MPLAB and MCC18 if the tools are installed elsewhere.
setlocal
if "%MPLAB%"=="" set MPLAB=C:\Program Files (x86)\Microchip\MPASM Suite
if "%MCC18%"=="" set MCC18=C:\Program Files (x86)\Microchip\mplabc18\v3.47
set MPASM=%MPLAB%\MPASMWIN.exe
set MPLINK=%MPLAB%\MPLink.exe
set CC=%MCC18%\bin\mcc18.exe
set CFLAGS=-p=18F26K80 -D_RASPBERRY_8 -I"." -I"LIB" -I"%MCC18%\h" -Ou- -Ot- -Ob- -Op- -Or- -Od- -Opa-
if not exist OBJ mkdir OBJ
if not exist BIN mkdir BIN
"%MPASM%" /q /p18F26K80 "LIB\SCS_UART.ASM" /l"OBJ\SCS_UART.lst" /e"OBJ\SCS_UART.err" /o"OBJ\SCS_UART.o" /dRASPBERRY_8
if errorlevel 1 goto fail
"%MPASM%" /q /p18F26K80 "LIB\CANREPRO_232_EVO.ASM" /l"OBJ\CANREPRO_232_EVO.lst" /e"OBJ\CANREPRO_232_EVO.err" /o"OBJ\CANREPRO_232_EVO.o" /dRASPBERRY_8
if errorlevel 1 goto fail
"%CC%" "ESPSCSGATE.C" -fo="OBJ\ESPSCSGATE.o" -fe="OBJ\ESPSCSGATE.err" %CFLAGS%
if errorlevel 1 goto fail
"%CC%" "LIB\DELAY.c" -fo="OBJ\DELAY.o" -fe="OBJ\DELAY.err" %CFLAGS%
if errorlevel 1 goto fail
"%MPLINK%" /p18F26K80 /l"%MCC18%\lib" /k"LIB" "LIB\18F26K80_B.LKR" "OBJ\ESPSCSGATE.o" "OBJ\CANREPRO_232_EVO.o" "OBJ\DELAY.o" "OBJ\SCS_UART.o" /u_CRUNTIME /z__MPLAB_BUILD=1 /m"BIN\espscsgate_RASPY_8.map" /w /o"BIN\espscsgate_RASPY_8.cof"
if errorlevel 1 goto fail
echo build OK: BIN\espscsgate_RASPY_8.hex
exit /b 0
:fail
echo BUILD FAILED (see OBJ\*.err)
exit /b 1
