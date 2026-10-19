# Privacy boundary

The AI decision-support service receives only a compact local-model summary: model type, score or class, threshold, session label and input-quality counts. It must not receive raw EEG/ECG values, uploaded files, email addresses, Auth0 identifiers or access tokens. Personal history is stored only as minimal decision metadata under the authenticated user's server-side profile identifier. History queries must be filtered to the verified caller and never accept a browser-supplied user identifier.
