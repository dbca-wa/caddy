import ast
import os


def env(key, default=None, required=False):
    """
    Retrieves environment variables and returns Python natives. The (optional)
    default will be returned if the environment variable does not exist.
    """
    if required and key not in os.environ:
        raise Exception(f"Missing required environment variable '{key}'")
    elif key in os.environ:
        value = os.environ[key]
    else:
        value = default

    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value
