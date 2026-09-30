import unittest

from llm import provider_config


class DockerOllamaConfigTests(unittest.TestCase):
    def test_host_bridge_requires_server_opt_in(self):
        env = {"LOCAL_LLM_BASE_URL": "http://host.docker.internal:11434/v1"}
        with self.assertRaises(ValueError):
            provider_config("local", env)
        env["LOCAL_LLM_ALLOW_DOCKER_HOST"] = "1"
        self.assertEqual(provider_config("local", env).base_url, env["LOCAL_LLM_BASE_URL"])

    def test_opt_in_does_not_allow_external_or_credentialed_urls(self):
        for url in ("https://ollama.com/v1", "http://192.168.1.5:11434/v1",
                    "http://host.docker.internal.evil.test/v1",
                    "http://user:password@host.docker.internal:11434/v1",
                    "http://host.docker.internal:11434/v1?api_key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                provider_config("local", {"LOCAL_LLM_BASE_URL": url, "LOCAL_LLM_ALLOW_DOCKER_HOST": "1"})


if __name__ == "__main__":
    unittest.main()
