import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react'
import { Profile, profileApi } from './api'
import { useTheme } from './theme'

interface ProfileContextType {
  profile: Profile | null
  error: boolean
  update: (changes: Parameters<typeof profileApi.update>[0]) => Promise<Profile>
  reload: () => void
}

const ProfileContext = createContext<ProfileContextType | undefined>(undefined)

// Loads the single local profile (name, theme, first-run status) and keeps the
// saved theme and the on-screen theme in step.
export function ProfileProvider({ children }: { children: ReactNode }) {
  const { theme, setTheme } = useTheme()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState(false)
  const applied = useRef(false)

  const reload = useCallback(() => {
    setError(false)
    profileApi.get().then((res) => {
      setProfile(res.data)
      if (!applied.current) {
        applied.current = true
        // No saved theme yet (upgraded from 0.1.0): keep the one on screen; the effect below saves it.
        if (res.data.onboarded && res.data.theme) setTheme(res.data.theme)
      }
    }).catch(() => setError(true))
  }, [setTheme])

  useEffect(() => { reload() }, [reload])

  // Remember theme changes made anywhere (sidebar toggle, Settings).
  useEffect(() => {
    if (profile?.onboarded && profile.theme !== theme) {
      profileApi.update({ theme }).then((res) => setProfile(res.data)).catch(() => undefined)
    }
  }, [theme, profile])

  const update = useCallback(async (changes: Parameters<typeof profileApi.update>[0]) => {
    const res = await profileApi.update(changes)
    setProfile(res.data)
    return res.data
  }, [])

  return <ProfileContext.Provider value={{ profile, error, update, reload }}>{children}</ProfileContext.Provider>
}

export function useProfile() {
  const context = useContext(ProfileContext)
  if (!context) throw new Error('useProfile must be used within ProfileProvider')
  return context
}
