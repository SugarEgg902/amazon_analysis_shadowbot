from curl_cffi import requests
from main import build_search_variables, get_api_headers

PROXY = "http://user:pass@gw.dataimpulse.com:823"
HOME  = "https://business.walmart.com/search"
GQL   = "https://business.walmart.com/orchestra/snb/graphql/Search/" \
        "213a5c885c92510bcb21ffbde07ead6b5b33ca6c4416fc9c531c1c80cd68a96a/search"

s = requests.Session()

# Step 1: Warmup — 获取 Akamai/F5 session cookies
s.get(HOME, params={"q": "baby food"}, impersonate="chrome",
      proxies={"https": PROXY}, timeout=60)

# Step 2: GraphQL 搜索
r = s.get(GQL,
    params={"variables": build_search_variables("baby food", 1, 40)},
    headers=get_api_headers("baby food"),
    impersonate="chrome", proxies={"https": PROXY}, timeout=60)

# Step 3: 提取商品数据
items = r.json()["data"]["search"]["searchResult"]["itemStacks"][0]["itemsV2"]
print(f"获取 {len(items)} 条商品")