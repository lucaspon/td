# Homepage

Static HTML, CSS, and JavaScript. The page reuses `assets/demo.gif` from the repo.
No build step or npm dependencies.

## Local preview

From the repository root:

```nu
python3 -m http.server 8080 --bind 127.0.0.1
```

Open `http://127.0.0.1:8080`. Stop the server after previewing. This serves the
repository locally; do not use it as a public production server.

## Publishing

In the repository's **Settings → Pages**, select **GitHub Actions** as the source.
The `Publish homepage` workflow deploys on pushes to `main` that change the site,
or when run manually. It uploads only `index.html`, `website/`, and the demo GIF.

For `td-cli.xyz`, add the custom domain in Pages settings, configure the DNS
records GitHub specifies, and enable HTTPS after the certificate is ready.
The domain currently points to Hostinger's parking page; adding the homepage
source alone does not change DNS.

The site uses relative asset URLs so it also works under the default
`https://lucaspon.github.io/td/` address.
