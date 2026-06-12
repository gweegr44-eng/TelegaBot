from google_auth_oauthlib.flow import Flow
import json

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def build_flow(client_config_path: str, redirect_uri: str = None):
    with open(client_config_path, 'r') as f:
        client_config = json.load(f)
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    return flow

def get_authorization_url(flow):
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    return auth_url, state

def exchange_code_for_credentials(flow, code: str):
    flow.fetch_token(code=code)
    return flow.credentials