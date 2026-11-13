import * as React from "react"
import { cn } from "cn"

/*
 * Tabela do shadcn ajustada à skill Frescor: cabeçalho 12px maiúsculo
 * --muted sobre --surface, linhas de 48px, zebra suave, realce verde ao
 * passar o mouse, texto 16px. Números à direita: passe
 * className="text-right numero" na célula.
 *
 * Por padrão a tabela vem dentro de um painel (raio 16px, contorno e
 * sombra). Tabela dentro de outra (as lojas de um produto) usa
 * `contorno={false}` para não virar um cartão dentro do cartão.
 */

function Table({
  className,
  contorno = true,
  ...props
}: React.ComponentProps<"table"> & { contorno?: boolean }) {
  return (
    <div
      data-slot="table-container"
      className={cn("relative w-full overflow-x-auto", contorno && "painel")}
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-base", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("bg-surface/80 [&_tr]:border-b [&_tr]:border-line", className)}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b border-line/70 transition-colors [tbody_&]:even:bg-surface/55 [tbody_&]:hover:bg-primary-soft/70",
        className
      )}
      {...props}
    />
  )
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-11 px-4 text-left align-middle text-xs font-semibold tracking-[0.06em] whitespace-nowrap text-muted-foreground uppercase",
        className
      )}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "h-12 px-4 py-2 align-middle",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
