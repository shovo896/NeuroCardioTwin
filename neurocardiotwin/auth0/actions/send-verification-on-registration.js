/**
 * Auth0 Post User Registration Action for NeuroCardioTwin.
 *
 * This Action has no browser or Vercel credentials.  Its only capability is
 * to ask Auth0 to deliver a verification link for a newly created user in the
 * configured database connection.  Secret values are set in Auth0 Actions.
 */
exports.onExecutePostUserRegistration = async (event) => {
  if (
    event.connection.strategy !== 'auth0' ||
    event.client.client_id !== event.secrets.NCT_WEB_CLIENT_ID ||
    event.user.email_verified
  ) return;

  const domain = event.secrets.NCT_AUTH0_DOMAIN;
  const tokenResponse = await fetch(`https://${domain}/oauth/token`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'client_credentials',
      client_id: event.secrets.NCT_VERIFY_MAILER_CLIENT_ID,
      client_secret: event.secrets.NCT_VERIFY_MAILER_CLIENT_SECRET,
      audience: `https://${domain}/api/v2/`,
    }),
  });
  if (!tokenResponse.ok) {
    console.error('Could not obtain the verification-mailer access token.');
    return;
  }

  const { access_token: accessToken } = await tokenResponse.json();
  const verificationResponse = await fetch(`https://${domain}/api/v2/jobs/verification-email`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${accessToken}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      user_id: event.user.user_id,
      client_id: event.client.client_id,
    }),
  });
  if (!verificationResponse.ok) {
    console.error('Could not queue the verification email.');
  }
};
