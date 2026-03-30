// PM2 Ecosystem Config for Counselling App
// Usage: pm2 start ecosystem.config.js

const workers = process.env.COUNSELLING_UVICORN_WORKERS || "2";

module.exports = {
  apps: [
    {
      name: "counselling",
      script: "uvicorn",
      args: `main:app --host 127.0.0.1 --port 5003 --workers ${workers}`,
      cwd: "/home/railway/counselling-app",
      interpreter: "none",
    },
  ],
};
