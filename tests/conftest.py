"""Keep legacy route tests on the local app regardless of deployment .env."""

import os


os.environ["APP_MODE"] = "local"
