.PHONY: test deploy clean

test:
	uv run pytest

deploy:
	rsync -az --delete site/ deploy@tasklog.example.com:/srv/www/tasklog/

clean:
	rm -rf build dist .venv site
