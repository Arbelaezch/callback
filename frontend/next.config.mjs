// console.log('[next.config] INTERNAL_API_URL=', process.env.INTERNAL_API_URL);

/** @type {import('next').NextConfig} */
const nextConfig = {
  watchOptions: {
    ignored: /node_modules/,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*/',       // match with trailing slash
        destination: `${process.env.INTERNAL_API_URL}/api/:path*/`,
      },
      {
        source: '/api/:path*',        // match without trailing slash
        destination: `${process.env.INTERNAL_API_URL}/api/:path*/`,  // add it
      },
    ];
  },
};

export default nextConfig;