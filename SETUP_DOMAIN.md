# Running Your App at insta.24x7stream.shop

## Prerequisites
- Your server's public IP address
- DNS access to manage `24x7stream.shop` domain
- Docker and Docker Compose installed
- Certbot installed (for SSL certificates)

## Setup Steps

### 1. DNS Configuration
Point your domain to your server's IP:
```
A record: insta.24x7stream.shop → your-server-ip
```

### 2. Create .env File
```bash
cp .env.example .env
# Edit .env with your credentials
nano .env
```

### 3. Generate SSL Certificate (Let's Encrypt)
```bash
# Install certbot if not already installed
sudo apt-get update && sudo apt-get install -y certbot python3-certbot-nginx

# Generate certificate
sudo certbot certonly --standalone -d insta.24x7stream.shop -d www.insta.24x7stream.shop

# Note the certificate paths:
# - Full chain: /etc/letsencrypt/live/insta.24x7stream.shop/fullchain.pem
# - Private key: /etc/letsencrypt/live/insta.24x7stream.shop/privkey.pem
```

### 4. Set Proper Permissions
```bash
# Allow the Docker app to read SSL certificates
sudo chmod 755 /etc/letsencrypt/live/
sudo chmod 755 /etc/letsencrypt/archive/
```

### 5. Start the Application
```bash
# Navigate to your project directory
cd /home/priyanka/projects/looplive

# Start with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f
```

### 6. Verify It's Working
```bash
curl https://insta.24x7stream.shop/
```

You should see the login page HTML.

## Auto-Renew SSL Certificates
```bash
# Add to crontab
sudo crontab -e

# Add this line (runs renewal check daily at 2 AM)
0 2 * * * /usr/bin/certbot renew --quiet && docker-compose -f /home/priyanka/projects/looplive/docker-compose.yml reload
```

## Troubleshooting

### Certificate Issues
```bash
# Check certificate validity
sudo openssl x509 -in /etc/letsencrypt/live/insta.24x7stream.shop/fullchain.pem -text -noout

# Renew immediately
sudo certbot renew --force-renewal
```

### Port Already in Use
```bash
# Check what's using port 80 or 443
sudo lsof -i :80
sudo lsof -i :443

# Kill the process if needed
sudo kill -9 <PID>
```

### Container Issues
```bash
# View logs
docker-compose logs -f nginx
docker-compose logs -f app

# Restart
docker-compose restart

# Full rebuild
docker-compose down
docker-compose up --build -d
```

## Access Your App
- **URL**: https://insta.24x7stream.shop
- **Default Username**: admin
- **Default Password**: changeme (change in .env file)

## Production Recommendations
1. Change `APP_PASSWORD` in `.env` to a strong password
2. Set a random `SECRET_KEY` in `.env`
3. Enable HTTP/2 in nginx (already configured)
4. Monitor logs regularly
5. Set up automated backups of `uploads/` and `ig_stream_config.json`
