import type { NextConfig } from "next";

const isGitHubPages = process.env.GITHUB_ACTIONS === "true";
const githubBasePath = isGitHubPages ? "/rastem_vmeste" : "";

const nextConfig: NextConfig = {
  output: isGitHubPages ? "export" : undefined,
  basePath: githubBasePath,
  assetPrefix: githubBasePath || undefined,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
