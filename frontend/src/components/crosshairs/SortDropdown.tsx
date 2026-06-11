import { Icon } from '@/components/primitives'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui'

interface SortOption<K extends string> {
  value: K
  label: string
  icon: string
}

interface Props<K extends string> {
  value: K
  onChange: (key: K) => void
  options: SortOption<K>[]
  dir?: 'asc' | 'desc'
  onDirChange?: (dir: 'asc' | 'desc') => void
}

export function SortDropdown<K extends string>({
  value,
  onChange,
  options,
  dir,
  onDirChange,
}: Props<K>) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          aria-label="排序"
          className="flex h-7 w-7 select-none items-center justify-center rounded-md hover:bg-accent"
        >
          <Icon
            icon="fa-solid fa-arrow-up-arrow-down"
            wrapperClassName="size-3"
            className="text-muted-foreground"
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-36">
        {options.map(opt => {
          const isActive = value === opt.value
          return (
            <DropdownMenuItem
              key={opt.value}
              onClick={() => {
                if (isActive && dir && onDirChange) {
                  onDirChange(dir === 'asc' ? 'desc' : 'asc')
                } else {
                  onChange(opt.value)
                }
              }}
            >
              <Icon icon={opt.icon} wrapperClassName="mr-2 size-4" />
              <span>{opt.label}</span>
              {isActive && dir ? (
                <Icon
                  icon={dir === 'asc' ? 'fa-solid fa-arrow-up' : 'fa-solid fa-arrow-down'}
                  wrapperClassName="ml-auto size-4"
                />
              ) : isActive ? (
                <Icon icon="fa-solid fa-check" wrapperClassName="ml-auto size-4" />
              ) : null}
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
