import unittest

from ingress import normalize_hostname, public_surface_allows, public_webhook_hostname


class PublicIngressTests(unittest.TestCase):
    def test_hostname_normalization_handles_case_trailing_dot_and_port(self):
        self.assertEqual(normalize_hostname("Telegram.Desando.Org.:443"), "telegram.desando.org")
        self.assertEqual(public_webhook_hostname("https://Telegram.Desando.Org"), "telegram.desando.org")

    def test_non_public_hosts_keep_local_operator_surface(self):
        for method, path in (("GET", "/health"), ("POST", "/webhook"), ("GET", "/docs")):
            self.assertTrue(
                public_surface_allows(
                    webhook_base_url="https://telegram.desando.org",
                    request_host="127.0.0.1:8787",
                    method=method,
                    path=path,
                )
            )

    def test_public_host_allows_only_exact_post_webhook(self):
        self.assertTrue(
            public_surface_allows(
                webhook_base_url="https://telegram.desando.org",
                request_host="telegram.desando.org",
                method="POST",
                path="/webhook",
            )
        )
        rejected = (
            ("GET", "/webhook"),
            ("POST", "/webhook/"),
            ("GET", "/health"),
            ("GET", "/docs"),
            ("POST", "/"),
        )
        for method, path in rejected:
            with self.subTest(method=method, path=path):
                self.assertFalse(
                    public_surface_allows(
                        webhook_base_url="https://telegram.desando.org",
                        request_host="telegram.desando.org:443",
                        method=method,
                        path=path,
                    )
                )


if __name__ == "__main__":
    unittest.main()
