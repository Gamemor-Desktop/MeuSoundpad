# Contribuindo

Obrigado pelo interesse! Contribuições são bem-vindas.

## Preparando o ambiente

```
pip install -r requirements-dev.txt
python soundpad.py
python -m pytest
```

O app é só para Windows. Os testes rodam no CI (GitHub Actions) a cada push e pull request.

## Antes de abrir um pull request

- Rode `python -m pytest` e confirme que tudo passa.
- Mantenha o estilo do código existente (nomes em português, comentários curtos).
- Faça mudanças pequenas e focadas, com a descrição do que mudou e por quê.
- **Não inclua áudios de terceiros** no repositório. A pasta `sons/` é ignorada de propósito.

## Reportando bugs

Use a aba Issues e inclua: versão do Windows, versão do app, o que você fez e o que aconteceu. Se possível, anexe o trecho relevante do `soundpad.log`, sem dados pessoais.
