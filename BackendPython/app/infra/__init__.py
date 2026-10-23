"""Adapters to the outside world that need more than the standard library or open
network connections: the AES ZIP writer and the SMTP mailer.

Only routers import this package. Services receive the objects built here as
parameters, so they stay testable with fakes and never touch smtplib or pyzipper.
"""
