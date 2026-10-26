"""Entrada: python -m hand_control."""

import argparse
from pathlib import Path
import sys

from .model import DEFAULT_MODEL, download_model


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Hand Control: LED virtual e volume por gestos.")
    parser.add_argument("--camera", type=int, default=0, help="índice /dev/videoN (padrão: 0)")
    parser.add_argument("--width", type=int, default=640, help="largura máxima: 640")
    parser.add_argument("--height", type=int, default=480, help="altura máxima: 480")
    parser.add_argument("--fps", type=int, default=15, help="limite de FPS, 1 a 30 (padrão: 15)")
    parser.add_argument("--threshold", type=float, default=0.6, help="confiança mínima, 0 a 1 (padrão: 0.6)")
    parser.add_argument("--no-volume-control", action="store_true",
                        help="desativa todo acesso ao áudio (inclusive leituras)")
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
                volume_control=not args.no_volume_control)
    except KeyboardInterrupt:
        print("\nHand Control encerrado.")
    except (ImportError, OSError) as exc:
        print(f"Erro ao carregar dependências: {exc}\n"
              "Execute bash scripts/setup.sh e consulte o diagnóstico no README.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Erro: {exc}\nConsulte o diagnóstico no README.md.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
