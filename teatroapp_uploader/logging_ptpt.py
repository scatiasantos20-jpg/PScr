# -*- coding: utf-8 -*-
"""Logging simples (PT-PT pré-Acordo)."""

class Logger:
    def __init__(self, prefix: str = "[Teatro.app]"):
        self.prefix = prefix

    def info(self, msg: str, *args):
        print(f"{self.prefix} INFORMAÇÃO: " + (msg % args if args else msg))

    def warning(self, msg: str, *args):
        print(f"{self.prefix} AVISO: " + (msg % args if args else msg))

    def error(self, msg: str, *args):
        print(f"{self.prefix} ERRO: " + (msg % args if args else msg))
