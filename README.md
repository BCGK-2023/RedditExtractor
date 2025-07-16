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
- 📊 **Multiple Output Formats** - JSON, CSV, RSS, XML for different use cases
- 🔄 **Asynchronous Processing** - Background jobs with webhook delivery for large datasets
- 📈 **Job Queue & Progress Tracking** - Monitor long-running scraping operations
- 🔧 **25+ Parameters** - Comprehensive control over scraping behavior
- ⚡ **Automation Ready** - Perfect for n8n, Zapier, and custom workflows
- 📚 **Built-in Documentation** - Interactive docs at `/docs`
- 🚨 **Professional Error Handling** - Proper error codes and actionable responses
- 🛡️ **Input Validation** - Comprehensive parameter validation

## 🔌 API Endpoints

### Main Scraping Endpoint
```http
POST /api/scrape
Content-Type: application/json
```

### Async Job Management
```http
GET /api/jobs/{jobId}     # Get job status and results
GET /api/jobs            # List recent jobs (with optional ?status= filter)
POST /api/webhook/test   # Test webhook URL connectivity
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

## 📖 Complete JSON Body Parameter Guide

### 📍 **Input Sources** (Choose One - Required)

#### `startUrls` (Array of Strings)
```json
{
  "startUrls": [
    "https://reddit.com/r/python",
    "https://reddit.com/user/someuser",
    "https://reddit.com/r/programming/comments/abc123/some_post"
  ]
}
```
**What it does**: Scrapes content from specific Reddit URLs  
**Use cases**: Target specific subreddits, users, or individual posts  
**Supported URL types**:
- Subreddits: `https://reddit.com/r/subreddit_name`
- Users: `https://reddit.com/user/username` 
- Posts: `https://reddit.com/r/subreddit/comments/post_id/title`
- Old Reddit URLs are also supported

#### `searchTerm` (String)
```json
{
  "searchTerm": "machine learning python"
}
```
**What it does**: Searches across all of Reddit for posts containing your search term  
**Use cases**: Find content about specific topics across multiple subreddits  
**Tips**: Use quotes for exact phrases, combine keywords for better results

---

### 🎯 **Content Control** (What to Scrape)

#### `searchForPosts` (Boolean, default: true)
```json
{
  "searchForPosts": true
}
```
**What it does**: Includes Reddit posts in the results  
**Use cases**: Turn off when you only want comments or user data

#### `searchForComments` (Boolean, default: true) 
```json
{
  "searchForComments": false
}
```
**What it does**: Includes comments from posts in the results  
**Use cases**: Turn off for faster scraping when you only need post data

#### `skipComments` (Boolean, default: false)
```json
{
  "skipComments": true
}
```
**What it does**: Completely skips comment scraping for better performance  
**Use cases**: When speed is more important than getting comment data

#### `includeNSFW` (Boolean, default: false)
```json
{
  "includeNSFW": true
}
```
**What it does**: Includes NSFW (Not Safe For Work) content in results  
**Use cases**: Research purposes, content moderation analysis

---

### 🔄 **Sorting & Filtering** (How to Order Results)

#### `sortSearch` (String, default: "hot")
```json
{
  "sortSearch": "top"
}
```
**What it does**: Controls how posts are sorted  
**Options**:
- `"hot"` - Reddit's "hot" algorithm (trending content)
- `"new"` - Newest posts first
- `"top"` - Highest scoring posts
- `"rising"` - Posts gaining momentum
- `"relevance"` - Most relevant to search term (for searches)

#### `filterByDate` (String, default: "all")
```json
{
  "filterByDate": "week"
}
```
**What it does**: Filters posts by time period  
**Options**: `"hour"`, `"day"`, `"week"`, `"month"`, `"year"`, `"all"`  
**Use cases**: Get recent content only, analyze trends over time

#### `postDateLimit` (ISO Date String, optional)
```json
{
  "postDateLimit": "2024-01-01T00:00:00Z"
}
```
**What it does**: Only include posts created after this date  
**Formats**: `"2024-01-01"` or `"2024-01-01T00:00:00Z"`  
**Use cases**: Incremental scraping, date range analysis

---

### 📊 **Output & Delivery**

#### `outputFormat` (String, default: "json")
```json
{
  "outputFormat": "csv"
}
```
**What it does**: Controls the format of returned data  
**Options**:
- `"json"` - Standard JSON response (default)
- `"csv"` - Downloadable CSV file for spreadsheet analysis
- `"rss"` - RSS feed for content syndication
- `"xml"` - XML format for legacy system integration

#### `webhookUrl` (String, optional)
```json
{
  "webhookUrl": "https://your-webhook.com/reddit-results"
}
```
**What it does**: Enables asynchronous processing - results sent to your webhook  
**Use cases**: Large scraping jobs, background processing, automation workflows  
**Note**: When provided, API returns job ID immediately instead of waiting

---

### 🔢 **Limits & Pagination** (How Much Data)

#### `maxItems` (Integer, default: 100, max: 10000)
```json
{
  "maxItems": 500
}
```
**What it does**: Maximum total items to return across all content types  
**Use cases**: Control response size, manage processing time

#### `postsPerPage` (Integer, default: 25, max: 100)
```json
{
  "postsPerPage": 50
}
```
**What it does**: How many posts to fetch per page during pagination  
**Use cases**: Performance tuning, memory management

#### `commentsPerPage` (Integer, default: 20, max: 100)
```json
{
  "commentsPerPage": 30
}
```
**What it does**: How many comments to fetch per post  
**Use cases**: Control comment depth, manage response size

---

### 📋 **Complete Example Requests**

#### Simple Subreddit Scraping
```json
{
  "startUrls": ["https://reddit.com/r/python"],
  "maxItems": 100,
  "sortSearch": "hot"
}
```

#### Advanced Search with Filtering
```json
{
  "searchTerm": "artificial intelligence",
  "searchForPosts": true,
  "searchForComments": false,
  "sortSearch": "relevance",
  "filterByDate": "month",
  "maxItems": 200,
  "includeNSFW": false
}
```

#### Async Processing with CSV Export
```json
{
  "searchTerm": "data science jobs",
  "maxItems": 1000,
  "outputFormat": "csv",
  "webhookUrl": "https://your-webhook.com/results",
  "sortSearch": "new",
  "filterByDate": "week"
}
```

#### User Analysis
```json
{
  "startUrls": ["https://reddit.com/user/someuser"],
  "searchForPosts": true,
  "skipComments": true,
  "maxItems": 500,
  "sortSearch": "new"
}
```

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
├── yars.py               # Core scraping logic
├── validator.py          # Parameter validation
├── formatters.py         # Output format handlers (JSON, CSV, RSS, XML)
├── jobs.py               # Job queue management
├── webhooks.py           # Webhook delivery system
├── background_worker.py  # Async job processing
├── url_parser.py         # URL parsing utilities
├── sessions.py           # Session management
├── agents.py             # User agent management
├── utils.py              # Utility functions
├── README.md             # Documentation
├── LICENSE               # License file
└── .gitignore            # Git configuration
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