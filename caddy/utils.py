import ast
import os


def env(key, default=None, required=False):
    """
    Retrieves environment variables and returns Python natives. The (optional)
    default will be returned if the environment variable does not exist.
    """
    if key in os.environ:
        value = os.environ[key]
    else:
        return

    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value
    except KeyError:
        if default or not required:
            return default
        raise Exception(f"Missing required environment variable '{key}'")
