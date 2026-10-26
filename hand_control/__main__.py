"""Entrada: python -m hand_control."""

import argparse
from pathlib import Path
import sys

from .model import DEFAULT_MODEL, download_model


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Smiley-Hand: LED, volume e mouse por gestos.")
    parser.add_argument("--camera", type=int, default=0, help="índice da câmera (padrão: 0)")
    parser.add_argument("--width", type=int, default=320, help="largura processada (padrão: 320; máximo: 640)")
    parser.add_argument("--height", type=int, default=240, help="altura processada (padrão: 240; máximo: 480)")
    parser.add_argument("--fps", type=int, default=15, help="limite de FPS, 1 a 30 (padrão: 15)")
    parser.add_argument("--threshold", type=float, default=0.6, help="confiança mínima, 0 a 1 (padrão: 0.6)")
    parser.add_argument("--no-volume-control", action="store_true",
                        help="desativa todo acesso ao áudio (inclusive leituras)")
    parser.add_argument("--no-mouse-control", action="store_true", help="desativa todo acesso ao cursor do sistema")
    parser.add_argument("--enable-virtual-led", action="store_true", help="demonstração: habilita LED e desativa o mouse")
    parser.add_argument("--mouse-margin", type=float, default=0.12,
                        help="margem normalizada da região de controle, 0 a 0.45 (padrão: 0.12)")
    parser.add_argument("--mouse-smoothing", type=float, default=0.25,
                        help="peso da nova posição na suavização, >0 até 1 (padrão: 0.25)")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="caminho do modelo .task")
    parser.add_argument("--download-model", action="store_true", help="baixa o modelo oficial e sai")
    args = parser.parse_args(argv)
    if args.camera < 0:
        parser.error("--camera deve ser >= 0")
    if not 160 <= args.width <= 640 or not 120 <= args.height <= 480:
        parser.error("resolução deve estar entre 160x120 e 640x480")
    if not 1 <= args.fps <= 30:
        parser.error("--fps deve estar entre 1 e 30")
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold deve estar entre 0 e 1")
    if not 0 <= args.mouse_margin <= 0.45:
        parser.error("--mouse-margin deve estar entre 0 e 0.45")
    if not 0 < args.mouse_smoothing <= 1:
        parser.error("--mouse-smoothing deve estar entre 0 (exclusivo) e 1")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.download_model:
            download_model(args.model)
        else:
            from .app import run

            run(model_path=args.model, camera=args.camera, width=args.width,
                height=args.height, fps=args.fps, threshold=args.threshold,
                volume_control=not args.no_volume_control, mouse_control=not args.no_mouse_control,
                mouse_margin=args.mouse_margin, mouse_smoothing=args.mouse_smoothing,
                enable_virtual_led=args.enable_virtual_led)
    except KeyboardInterrupt:
        print("\nSmiley-Hand encerrado.")
    except (ImportError, OSError) as exc:
        print(f"Erro ao carregar dependências: {exc}\n"
              "Instale as dependências na venv conforme o README da sua plataforma.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Erro: {exc}\nConsulte o diagnóstico no README.md.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
