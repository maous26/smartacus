/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker deployment
  output: 'standalone',

  // API rewrites to backend
  // In production (Railway), set NEXT_PUBLIC_BACKEND_URL to the backend service URL
  // e.g. NEXT_PUBLIC_BACKEND_URL=https://smartacus-api.up.railway.app
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
