// PM2 Ecosystem Config for Counselling App
// Save as: ecosystem.config.js
// Usage: pm2 start ecosystem.config.js

module.exports = {
  apps: [
    {
      name: "counselling",
      script: "uvicorn",
      args: "main:app --host 127.0.0.1 --port 5003",
      cwd: "/home/railway/counselling-app",
      interpreter: "none",
      env: {
        ROOT_PATH: "/counselling",
        DB_HOST: "localhost",
        DB_USER: "root",
        DB_PASSWORD: "",
        DB_NAME: "bbtro",
      },
    },
  ],
};
