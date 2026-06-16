/**
 * LiveKit connection helpers for TaskButler.
 * Centralises token fetching and URL resolution.
 */

const BACKEND =
  process.env.REACT_APP_BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "";

function api(path: string): string {
  return BACKEND ? `${BACKEND.replace(/\/$/, "")}${path}` : path;
}

export interface TokenResponse {
  url: string;
  token: string;
}

/**
 * Fetch a LiveKit access token from the backend.
 * @param room - the room (session) identifier
 * @param identity - user identity (email)
 * @param voiceGender - "male" | "female"
 */
export async function fetchLiveKitToken(
  room: string,
  identity: string,
  voiceGender: string = "female"
): Promise<TokenResponse> {
  const res = await fetch(
    api(
      `/api/token?room=${encodeURIComponent(room)}&identity=${encodeURIComponent(identity)}&voice_gender=${voiceGender}`
    )
  );
  if (!res.ok) {
    throw new Error(`Token request failed: ${res.status}`);
  }
  const data = await res.json();
  return {
    url: data.url || data.ws_url || "",
    token: data.token || data.access_token || "",
  };
}

/**
 * Returns the LiveKit server URL from environment config.
 */
export function getLiveKitUrl(): string {
  return (
    process.env.NEXT_PUBLIC_LIVEKIT_URL ||
    process.env.REACT_APP_LIVEKIT_URL ||
    ""
  );
}
