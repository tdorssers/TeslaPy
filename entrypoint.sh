#!/bin/sh

# Sets script to fail if any command fails.
set -e

run_cli() {
        python cli.py $@
}

run_menu() {
        python menu.py $@
}

run_gui() {
        python gui.py $@
}

print_usage() {
echo "

usage:	$0 COMMAND

commands:
  cli			run the CLI script
  menu			run the menu version
  gui			run the GUI (make sure you have X11 running and accessible)
  help		        Print this help
"
}

case "$1" in
    help)
        print_usage
        ;;
    cli)
	shift 1
        run_cli "$@"
        ;;
    menu)
	shift 1
        run_menu "$@"
        ;;
    gui)
	shift 1
        run_gui "$@"
        ;;
    *)
        exec "$@"
esac
