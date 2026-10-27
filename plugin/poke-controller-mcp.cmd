@echo off
rem Poke-Controller's MCP server for the Claude Code and Codex plugins.
rem It starts the installed app's PokeControllerMCP.exe; stdio passes straight through cmd.
rem POKECONTROLLER_MCP overrides the path (a portable copy or a source checkout's launcher).
rem Messages are ASCII: cmd reads this file in the console's code page. stdout is the MCP connection.
setlocal
set "EXE=%POKECONTROLLER_MCP%"
if not defined EXE set "EXE=%LOCALAPPDATA%\Programs\PokeController\PokeControllerMCP.exe"
if not exist "%EXE%" (
  echo Poke-Controller is not installed: %EXE% was not found. 1>&2
  echo Install it with: irm https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/releases/latest/download/get.ps1 ^| iex 1>&2
  exit /b 1
)
"%EXE%" %*
exit /b %errorlevel%
