# Gunicorn configuration settings.

bind = ":8080"
workers = 2
preload_app = True
# Disable access logging.
accesslog = None
