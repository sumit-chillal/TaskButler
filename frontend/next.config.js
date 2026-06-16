/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Expose the Emergent platform's REACT_APP_BACKEND_URL to client code so
  // we can call /api/* endpoints from React components.
  env: {
    REACT_APP_BACKEND_URL: process.env.REACT_APP_BACKEND_URL,
    NEXT_PUBLIC_LIVEKIT_URL: process.env.NEXT_PUBLIC_LIVEKIT_URL,
    NEXT_PUBLIC_LIVEKIT_TOKEN_ENDPOINT: process.env.NEXT_PUBLIC_LIVEKIT_TOKEN_ENDPOINT,
  },
};
module.exports = nextConfig;
