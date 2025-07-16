# 🔍 RedditExtractor

**A professional, proxy-enabled Reddit scraping API. Deploy to Railway in one click.**

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/your-template-id)

---

## 🎯 About RedditExtractor

RedditExtractor is a powerful, production-ready API for scraping Reddit. It comes with full proxy support, a flexible API for fetching posts, comments, and user data, and is designed for seamless integration with n8n, Zapier, or any custom workflow.

**This is the first tool in the Extractor Suite** - a series of professional scraping APIs designed for the modern automation stack.

## 🚀 Quick Start

1. **Deploy to Railway** - Click the button above
2. **Set Environment Variables** (optional - for proxy support):
   ```env
   PROXY_HOST=your-proxy-host
   PROXY_PORT=your-proxy-port
   PROXY_USERNAME=your-username
   PROXY_PASSWORD=your-password
   ```
3. **Start Scraping** - Your API is ready at `https://your-app.railway.app`

## 📋 Features

- 🎯 **URL-based & Search-based Scraping** - Scrape specific subreddits, users, or search across Reddit
- 🔄 **Proxy Support** - Built-in proxy integration for production use
- 📊 **Structured JSON Responses** - Clean, consistent API responses
- 🔧 **25+ Parameters** - Comprehensive control over scraping behavior
- ⚡ **Automation Ready** - Perfect for n8n, Zapier, and custom workflows
- 📈 **Built-in Documentation** - Interactive docs at `/docs`
- 🚨 **Error Handling** - Proper error codes and detailed responses
- 🛡️ **Input Validation** - Comprehensive parameter validation

## 🔌 API Endpoints

### Main Scraping Endpoint
```http
POST /api/scrape
Content-Type: application/json
```

### Health & Status
```http
GET /health          # API health check
GET /test-proxy      # Proxy connectivity test
GET /docs           # Interactive documentation
```

## 💡 Usage Examples

### 1. Scrape Subreddit Posts
```json
{
  "startUrls": ["https://reddit.com/r/python"],
  "searchForPosts": true,
  "maxItems": 50,
  "sortSearch": "hot",
  "filterByDate": "week"
}
```

### 2. Search Across Reddit
```json
{
  "searchTerm": "machine learning",
  "searchForPosts": true,
  "sortSearch": "relevance",
  "filterByDate": "month",
  "maxItems": 200
}
```

### 3. User-Specific Scraping
```json
{
  "startUrls": ["https://reddit.com/user/someuser"],
  "searchForPosts": true,
  "skipComments": true,
  "maxItems": 100
}
```

## 📖 Complete Parameter Reference

### Input Sources (Choose One)
- **`startUrls`** - Array of Reddit URLs to scrape
- **`searchTerm`** - Search query for Reddit-wide search

### Content Control
- **`searchForPosts`** - Include posts (default: true)
- **`searchForComments`** - Include comments (default: true)
- **`skipComments`** - Skip comment scraping for performance
- **`includeNSFW`** - Include NSFW content (default: false)

### Sorting & Filtering
- **`sortSearch`** - Sort order: "hot", "new", "top", "rising", "relevance"
- **`filterByDate`** - Time filter: "hour", "day", "week", "month", "year", "all"
- **`postDateLimit`** - ISO date string to filter posts after date

### Limits & Pagination
- **`maxItems`** - Maximum items to return (1-10000)
- **`postsPerPage`** - Posts per page (1-100)
- **`commentsPerPage`** - Comments per page (1-100)

## 📊 Response Format

### Success Response
```json
{
  "success": true,
  "data": {
    "posts": [...],
    "comments": [...],
    "users": [...],
    "communities": [...]
  },
  "metadata": {
    "totalItems": 150,
    "itemsReturned": 100,
    "requestParams": {...},
    "scrapedAt": "2025-07-16T17:00:07Z",
    "executionTime": "2.3s"
  },
  "errors": []
}
```

### Error Response
```json
{
  "success": false,
  "data": null,
  "metadata": {
    "requestParams": {...},
    "scrapedAt": "2025-07-16T17:00:07Z"
  },
  "errors": [
    {
      "code": "PROXY_ERROR",
      "message": "Proxy connection failed",
      "details": "Connection timeout after 10 seconds"
    }
  ]
}
```

## 🔗 Automation Integration

RedditExtractor is designed for seamless integration with automation platforms:

### n8n HTTP Request Node
```javascript
Method: POST
URL: https://your-app.railway.app/api/scrape
Headers: Content-Type: application/json
Body: {
  "startUrls": ["https://reddit.com/r/{{$json.subreddit}}"],
  "maxItems": {{$json.limit}},
  "sortSearch": "{{$json.sort}}"
}
```

### Zapier Webhooks
```javascript
URL: https://your-app.railway.app/api/scrape
Method: POST
Headers: Content-Type: application/json
Data: {
  "searchTerm": "{{inputData.query}}",
  "maxItems": 50,
  "sortSearch": "relevance"
}
```

The structured response format makes it easy to process results in subsequent workflow nodes.

## 🛠️ Local Development

### Prerequisites
- Python 3.8+
- pip or uv package manager

### Installation
```bash
git clone https://github.com/your-username/reddit-extractor.git
cd reddit-extractor
pip install -r requirements.txt
```

### Environment Variables
```env
# Optional: Proxy configuration
PROXY_HOST=your-proxy-host
PROXY_PORT=your-proxy-port
PROXY_USERNAME=your-username
PROXY_PASSWORD=your-password

# Server configuration
PORT=8000
```

### Run Locally
```bash
python app.py
```

API will be available at `http://localhost:8000`

## 🚨 Error Codes

| Code | Description | Recommended Action |
|------|-------------|-------------------|
| `PROXY_ERROR` | Proxy connection issues | Check proxy configuration and network connectivity |
| `REDDIT_BLOCKED` | Reddit blocking requests | Use a proxy or wait before retrying |
| `INVALID_PARAMS` | Parameter validation failed | Check parameter values and types |
| `TIMEOUT` | Request timeout | Try reducing maxItems or check network connection |
| `RATE_LIMITED` | Reddit rate limiting | Wait a few minutes before making another request |
| `INVALID_RESPONSE` | Invalid response from Reddit | The requested content may not exist or be available |

## 📁 Project Structure

```
reddit-extractor/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── Procfile              # Railway deployment config
├── src/
│   └── yars/
│       ├── yars.py       # Core scraping logic
│       ├── validator.py  # Parameter validation
│       ├── url_parser.py # URL parsing utilities
│       ├── sessions.py   # Session management
│       └── utils.py      # Utility functions
└── example/
    └── example.py        # Usage examples
```

## 🔒 Security & Best Practices

- ✅ **Proxy Support** - Built-in proxy integration for IP rotation
- ✅ **Rate Limiting** - Respects Reddit's rate limits
- ✅ **Input Validation** - Comprehensive parameter validation
- ✅ **Error Handling** - Graceful error handling and logging
- ✅ **No API Keys** - Uses Reddit's public JSON endpoints

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🆘 Support

- 📖 **Documentation**: Visit `/docs` on your deployed instance
- 🐛 **Issues**: [GitHub Issues](https://github.com/your-username/reddit-extractor/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/your-username/reddit-extractor/discussions)

## 🚀 Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/your-template-id)

---

## 🙏 Acknowledgements

RedditExtractor builds upon the solid foundation of the open-source project **YARS (Yet Another Reddit Scraper)**. We've heavily modified and enhanced it to create a professional, deployable API product.

---

**Built with ❤️ for the modern automation stack**