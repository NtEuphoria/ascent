#!/bin/bash
# Double-click this to shut the ASCENT server down.
PORT=8501
echo "Stopping the ASCENT server on port ${PORT}..."

PIDS=$(/usr/sbin/lsof -ti tcp:${PORT} 2>/dev/null)
if [ -z "$PIDS" ]; then
    echo "Nothing was running. Done."
else
    for pid in $PIDS; do
        kill "$pid" 2>/dev/null && echo "  stopped process $pid"
    done
    sleep 1
    echo "Done."
fi
echo
echo "This window can be closed."
