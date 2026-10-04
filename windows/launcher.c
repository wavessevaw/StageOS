#ifndef UNICODE
#define UNICODE
#endif
#define _UNICODE
#include <windows.h>
#include <wchar.h>
#include <stdlib.h>
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR argument,int show) {
    WCHAR root[32768], python[32768], command[65536];
    if(!GetModuleFileNameW(NULL,root,32768))return 1;
    WCHAR *slash=wcsrchr(root,L'\\');if(!slash)return 2;*slash=0;
    swprintf(python,32768,L"%ls\\runtime\\pythonw.exe",root);
    if(GetFileAttributesW(python)==INVALID_FILE_ATTRIBUTES){MessageBoxW(NULL,L"Не найден встроенный runtime. Распакуйте всю папку StageOS-Portable и запустите StageOS.exe.",L"StageOS",MB_OK|MB_ICONERROR);return 3;}
    swprintf(command,65536,L"\"%ls\" \"%ls\\app\\windows_desktop.py\" %ls",python,root,wcsstr(argument,L"--self-test")?L"--self-test":L"");
    STARTUPINFOW start={0};PROCESS_INFORMATION process={0};start.cb=sizeof(start);
    if(!CreateProcessW(python,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,root,&start,&process)) {MessageBoxW(NULL,L"Не удалось запустить StageOS. Убедитесь, что папка полностью распакована и не заблокирована Windows.",L"StageOS",MB_OK|MB_ICONERROR);return 4;}
    CloseHandle(process.hThread);WaitForSingleObject(process.hProcess,INFINITE);DWORD result=0;GetExitCodeProcess(process.hProcess,&result);CloseHandle(process.hProcess);return result;
}
