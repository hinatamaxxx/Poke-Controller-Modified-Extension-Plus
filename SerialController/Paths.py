"""Settings folders shared by the GUI modules. app.py points them to the installed locations first. MIT."""
import os

PROFILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
LOGS = "log"
