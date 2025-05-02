name: Filter Clash Nodes
on:
  push:
    branches:
      - main
  workflow_dispatch:
jobs:
  filter-nodes:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install pyyaml requests
      - name: Create data directory
        run: |
          mkdir -p data
      - name: Test network connectivity
        run: |
          curl -I https://www.github.com || echo "无法访问 GitHub"
      - name: Test proxy server connectivity
        run: |
          for proxy in $(grep 'server:' data/clash.yaml | awk '{print $2}'); do
            echo "Testing $proxy"
            curl -m 5 http://$proxy || echo "无法访问 $proxy"
          done
      - name: Run filter script
        run: |
          python filter_nodes.py
      - name: Upload result as artifact
        uses: actions/upload-artifact@v4
        with:
          name: google-yaml
          path: data/google.yaml
