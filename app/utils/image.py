"""Validação e pré-processamento de imagens.

O modelo ViT-Large/iNat21 espera entradas 224×224. Centralizamos aqui o resize e
a validação para que `vision.py` (e futuros clientes de modelo) não dupliquem
essa lógica e para que entradas inválidas sejam rejeitadas cedo, com erro claro.
"""

import io

from PIL import Image, UnidentifiedImageError

# O ViT-Large/patch16-224 do iNat21 foi treinado em 224×224.
TARGET_SIZE: tuple[int, int] = (224, 224)


class ImageValidationError(ValueError):
    """A entrada não é uma imagem válida ou não pôde ser processada."""


def preprocess_image(image_bytes: bytes, size: tuple[int, int] = TARGET_SIZE) -> bytes:
    """Valida, converte para RGB e redimensiona a imagem para `size`.

    Retorna os bytes JPEG prontos para envio ao endpoint de inferência.
    Levanta `ImageValidationError` se os bytes não forem uma imagem decodificável.
    """
    if not image_bytes:
        raise ImageValidationError("Imagem vazia: nenhum byte recebido.")

    try:
        # verify() detecta corrupção mas inutiliza o objeto — por isso reabrimos
        # os bytes em seguida para de fato manipular a imagem.
        Image.open(io.BytesIO(image_bytes)).verify()
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError(f"Não foi possível decodificar a imagem: {exc}") from exc

    # LANCZOS preserva detalhes ao reduzir fotos de alta resolução para 224×224.
    img = img.resize(size, Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()
