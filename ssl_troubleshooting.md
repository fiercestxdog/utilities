# LangSmith SSL Troubleshooting (Corporate Networks)

SSL errors in corporate environments almost always come from one of two sources:
**your company's proxy doing SSL inspection** (most common) or **LangSmith tracing
being enabled unintentionally** by a LangChain environment variable.

---

## 1. Check if LangSmith tracing is even enabled

LangChain silently enables LangSmith tracing if `LANGCHAIN_TRACING_V2=true` is set.
If you didn't set this intentionally, disable it first:

```bash
# Check if it's set
echo $LANGCHAIN_TRACING_V2        # Linux/Mac
echo $env:LANGCHAIN_TRACING_V2    # PowerShell
```

Disable it in your script or `.env`:
```python
os.environ["LANGCHAIN_TRACING_V2"] = "false"
```
If the SSL errors stop, tracing was the culprit and the steps below address the root cause.

---

## 2. Identify the SSL error type

Run this and share the exact message with your IT/security team:
```bash
python -c "import ssl; import urllib.request; urllib.request.urlopen('https://api.smith.langchain.com')"
```

Common error patterns and what they mean:

| Error message | Cause |
|---|---|
| `CERTIFICATE_VERIFY_FAILED` | Corporate CA cert not trusted by Python |
| `unable to get local issuer certificate` | Proxy is re-signing certs with an internal CA |
| `WRONG_VERSION_NUMBER` | Traffic is being intercepted before TLS handshake |
| `Connection refused` / timeout | Firewall is blocking `api.smith.langchain.com` entirely |

---

## 3. Corporate proxy / SSL inspection (most likely cause)

Your company's proxy intercepts HTTPS traffic and re-signs it with an internal CA
certificate. Python doesn't trust that CA by default.

**Fix — inject the corporate CA bundle:**
```python
import os
# Path to your company's CA bundle (.pem or .crt) — get this from IT
os.environ["REQUESTS_CA_BUNDLE"]  = r"C:\path\to\corporate-ca-bundle.pem"
os.environ["SSL_CERT_FILE"]       = r"C:\path\to\corporate-ca-bundle.pem"
os.environ["CURL_CA_BUNDLE"]      = r"C:\path\to\corporate-ca-bundle.pem"
```

Add these **before** any LangChain imports. To find the cert path, ask IT or export
it from your browser:
- Chrome: Settings → Privacy → Manage Certificates → export the root CA

**Or append the cert to Python's default bundle:**
```bash
python -c "import certifi; print(certifi.where())"
# Then append your corporate cert to that file
```

---

## 4. Disable SSL verification (temporary diagnosis only)

**Never use this in production**, but useful to confirm SSL inspection is the cause:
```python
import os, httpx
os.environ["LANGCHAIN_TRACING_V2"] = "true"
# Monkey-patch httpx to skip verification
_orig = httpx.Client.__init__
def _patched(self, *a, **kw):
    kw["verify"] = False
    _orig(self, *a, **kw)
httpx.Client.__init__ = _patched
```
If this makes the error go away, your corporate CA is the confirmed issue.

---

## 5. Check proxy environment variables

LangSmith's client uses `httpx` which respects standard proxy vars:
```bash
echo $HTTPS_PROXY
echo $HTTP_PROXY
echo $NO_PROXY
```
If `HTTPS_PROXY` is set to your corporate proxy but the CA bundle isn't configured,
every HTTPS call will fail. Either set `REQUESTS_CA_BUNDLE` (step 3) or add the
endpoints to `NO_PROXY`:
```python
os.environ["NO_PROXY"] = "api.smith.langchain.com,api.openai.com"
```

---

## 6. Ask IT to allowlist the endpoints

If you need LangSmith tracing at work, ask your network/security team to allowlist:
- `api.smith.langchain.com` (tracing)
- `api.openai.com` (LLM calls)

---

## Quick checklist

```
[ ] LANGCHAIN_TRACING_V2 unintentionally set to true?
[ ] Corporate CA bundle trusted by Python (REQUESTS_CA_BUNDLE)?
[ ] HTTPS_PROXY set but CA bundle not configured?
[ ] api.smith.langchain.com reachable at all (firewall block)?
[ ] Python certifi package up to date? (pip install --upgrade certifi)
```
