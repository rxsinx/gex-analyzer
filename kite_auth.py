from kiteconnect import KiteConnect

class KiteManager:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.kite = KiteConnect(api_key=api_key)

    def get_login_url(self):
        return self.kite.login_url()

    def create_session(self, request_token):
        data = self.kite.generate_session(request_token, api_secret=self.api_secret)
        self.kite.set_access_token(data["access_token"])
        return self.kite
