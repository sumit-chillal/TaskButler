/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  output: 'export',

  env: {
    REACT_APP_BACKEND_URL: process.env.REACT_APP_BACKEND_URL,
    NEXT_PUBLIC_LIVEKIT_URL: process.env.NEXT_PUBLIC_LIVEKIT_URL,
    NEXT_PUBLIC_LIVEKIT_TOKEN_ENDPOINT:
      process.env.NEXT_PUBLIC_LIVEKIT_TOKEN_ENDPOINT,
  },
};

module.exports = nextConfig;
