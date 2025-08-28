import os
import json

APP_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

def ensure_config():
    if not os.path.exists(CONFIG_PATH):
        cfg = {
            "categories": [
                "Groceries",
                "Restaurants",
                "Housing",
                "Transport",
                "Family",
                "Personal",
                "Other",
            ],
            "budgets": {},
            "firebase_url": ""
        }
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        return cfg
    with open(CONFIG_PATH) as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
