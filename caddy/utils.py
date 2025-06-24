import ast
import os


def env(key, default=None, required=False):
    """
    Retrieves environment variables and returns Python natives. The (optional)
    default will be returned if the environment variable does not exist.
    """
    value = os.environ[key]
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value
    except KeyError:
        if default or not required:
            return default
        raise Exception(f"Missing required environment variable '{key}'")
