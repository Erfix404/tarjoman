## Configuration

By default, the server listens on port 8080. You can override this by setting the `PORT` environment variable. If you're running behind a reverse proxy, make sure to set `TRUST_PROXY=1`, otherwise client IPs will be logged incorrectly.

> **Warning:** Rotating the `SECRET_KEY` will invalidate all existing sessions. Users will be logged out and will need to sign in again.

To run the test suite, use:

```bash
make test
```

If a test fails with `ConnectionRefusedError`, the database probably isn't up yet. Wait a few seconds and try again.

## UI strings

- `delete_confirm`: "Delete {count} files? This can't be undone."
- `setup_done`: "You're all set!"
- `offline`: "Couldn't connect. Check your internet connection and try again."
