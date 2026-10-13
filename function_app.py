# The Functions host loads function_app.py from the project root; the app itself lives in pet_claims_function/.
from pet_claims_function.function_app import app  # noqa: F401
