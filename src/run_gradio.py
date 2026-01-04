"""
Wrapper für die Gradio-App
"""

import sys
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

GRADIO_PORT = 7860


def kill_process_on_port(port: int) -> bool:
    """
    Beendet Prozesse, die den angegebenen Port belegen (Windows).

    Args:
        port: Port-Nummer

    Returns:
        True wenn ein Prozess beendet wurde, False sonst
    """
    if sys.platform != "win32":
        #Linux/Mac: Andere Methode
        try:
            result = subprocess.run(
                f"lsof -ti:{port} | xargs kill -9",
                shell=True,
                capture_output=True
            )
            return result.returncode == 0
        except Exception:
            return False

    try:
        #Windows: netstat nutzen um PID zu finden
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )

        pids_to_kill = set()
        for line in result.stdout.splitlines():
            #Suche nach "ABHÖREN" (listening) auf unserem Port
            if f":{port}" in line and ("ABHÖREN" in line or "LISTENING" in line):
                parts = line.split()
                if parts:
                    try:
                        pid = int(parts[-1])
                        #Eigenen Prozess nicht killen
                        if pid != os.getpid():
                            pids_to_kill.add(pid)
                    except ValueError:
                        continue

        if not pids_to_kill:
            return False

        #Prozesse beenden
        killed = False
        for pid in pids_to_kill:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                print(f"  Alte Instanz beendet (PID: {pid})")
                killed = True
            except Exception as e:
                logger.warning(f"Konnte Prozess {pid} nicht beenden: {e}")

        return killed

    except Exception as e:
        logger.warning(f"Fehler beim Prüfen des Ports: {e}")
        return False


if __name__ == "__main__":
    try:
        print("=" * 60)
        print("Discord Voice Bot - Gradio Version")
        print("=" * 60)
        print()

        #Alte Instanzen beenden falls Port belegt
        print("Prüfe Port 7860...")
        if kill_process_on_port(GRADIO_PORT):
            print("  Alte Instanz(en) beendet.")
            #Kurz warten bis Port freigegeben ist
            import time
            time.sleep(0.5)
        else:
            print("  Port ist frei.")

        print()
        print("Starte Web-Interface...")
        print(f"Browser öffnet automatisch: http://localhost:{GRADIO_PORT}")
        print()
        print("Zum Beenden: Strg+C drücken")
        print("=" * 60)
        print()

        #Importiere und starte gradio_app
        from gradio_app import create_interface

        #Interface erstellen
        demo = create_interface()

        #Starten
        demo.launch(
            server_name="0.0.0.0",
            server_port=GRADIO_PORT,
            share=False,  #Setze auf True für öffentlichen Link
            show_error=True,
            inbrowser=True  #Öffne Browser automatisch
        )

    except KeyboardInterrupt:
        print("\n\nBot wird beendet...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fehler beim Start: {e}", exc_info=True)
        print(f"\n Fehler: {e}")
        sys.exit(1)
